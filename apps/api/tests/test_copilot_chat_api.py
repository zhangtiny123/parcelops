from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.session import reset_database_state
from app.main import create_app
from app.models.billing import ParcelInvoiceLine
from app.models.copilot import CopilotTrace
from app.models.fulfillment import OrderRecord, Shipment
from app.models.recovery import RecoveryCase, RecoveryIssue
from app.models.common import utcnow
from app.settings import reset_settings_cache
from conftest import run_migrations


def _configure_test_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_name: str,
) -> str:
    database_url = f"sqlite:///{tmp_path / database_name}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("COPILOT_PROVIDER", "heuristic")

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def _seed_copilot_records(database_url: str) -> None:
    now = utcnow()
    order = OrderRecord(
        id="order-1",
        external_order_id="SO-1001",
        customer_ref="customer-1001",
        order_date=now - timedelta(days=12),
        promised_service_level="Ground",
        warehouse_id="PHL-1",
    )
    shipment = Shipment(
        id="shipment-1",
        external_shipment_id="ext-shipment-1",
        order_id=order.id,
        tracking_number="1Z999AA10123456784",
        carrier="UPS",
        service_level="Ground",
        origin_zip="19104",
        destination_zip="10001",
        zone="4",
        weight_lb=Decimal("4.20"),
        dim_weight_lb=Decimal("5.10"),
        shipped_at=now - timedelta(days=11),
        delivered_at=now - timedelta(days=8),
        warehouse_id="PHL-1",
    )
    parcel_invoice_line = ParcelInvoiceLine(
        id="parcel-line-1",
        invoice_number="INV-1001",
        invoice_date=(now - timedelta(days=10)).date(),
        tracking_number=shipment.tracking_number,
        carrier="UPS",
        charge_type="transportation",
        amount=Decimal("18.75"),
        currency="USD",
        shipment_id=shipment.id,
        raw_row_ref="parcel.csv:2",
    )
    issues = [
        RecoveryIssue(
            id="issue-1",
            issue_type="billed_weight_mismatch",
            provider_name="UPS",
            severity="high",
            status="open",
            confidence=Decimal("0.9300"),
            estimated_recoverable_amount=Decimal("12.50"),
            shipment_id=shipment.id,
            parcel_invoice_line_id=parcel_invoice_line.id,
            summary="Billed weight exceeds the modeled shipment weight.",
            evidence_json={
                "invoice_number": "INV-1001",
                "tracking_number": shipment.tracking_number,
            },
            detected_at=now - timedelta(days=3),
        ),
        RecoveryIssue(
            id="issue-2",
            issue_type="duplicate_charge",
            provider_name="UPS",
            severity="medium",
            status="open",
            confidence=Decimal("0.8800"),
            estimated_recoverable_amount=Decimal("6.25"),
            parcel_invoice_line_id=parcel_invoice_line.id,
            summary="The same parcel line appears to have been billed twice.",
            evidence_json={"invoice_number": "INV-1001", "duplicate_count": 2},
            detected_at=now - timedelta(days=2),
        ),
        RecoveryIssue(
            id="issue-3",
            issue_type="duplicate_charge",
            provider_name="FedEx",
            severity="low",
            status="resolved",
            confidence=Decimal("0.7000"),
            estimated_recoverable_amount=Decimal("4.00"),
            summary="Prior-period issue used to validate dashboard deltas.",
            evidence_json={"invoice_number": "INV-2001"},
            detected_at=now - timedelta(days=45),
        ),
    ]

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            session.add(order)
            session.add(shipment)
            session.add(parcel_invoice_line)
            session.add_all(issues)
            session.commit()
    finally:
        engine.dispose()


def _load_traces(database_url: str) -> list[CopilotTrace]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            return list(
                session.scalars(
                    select(CopilotTrace).order_by(
                        CopilotTrace.created_at.asc(),
                        CopilotTrace.id.asc(),
                    )
                )
            )
    finally:
        engine.dispose()


def test_copilot_chat_returns_grounded_top_recoveries_and_persists_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-top-recoveries.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Which open issues represent the highest recoverable amount right now?",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["tool_calls"][0]["name"] == "search_issues"
    assert payload["tool_calls"][0]["arguments"]["status"] == "open"
    assert payload["tool_calls"][0]["arguments"]["sort_by"] == "recoverable_amount_desc"
    assert payload["tool_calls"][0]["arguments"]["limit"] == 5
    assert "issue-1" in payload["message"]
    assert "$12.50" in payload["message"]
    assert payload["references"][0]["id"] == "issue-1"

    traces = _load_traces(database_url)
    assert len(traces) == 1
    assert traces[0].status == "completed"
    assert traces[0].request_messages_json[0]["content"].startswith("Which open issues")
    assert traces[0].tool_calls_json[0]["name"] == "search_issues"
    assert traces[0].response_text == payload["message"]


def test_copilot_chat_returns_dashboard_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-dashboard.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Give me dashboard metrics for the last 30 days.",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["tool_calls"][0]["name"] == "get_dashboard_metrics"
    assert "last 30 days" in payload["message"]
    assert "$18.75" in payload["message"]
    assert "UPS" in payload["message"]


def test_copilot_chat_looks_up_shipments_by_tracking_number(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-shipment.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Look up shipment 1Z999AA10123456784.",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["name"] == "lookup_shipment"
    assert "shipment-1" in payload["message"]
    assert "issue-1" in payload["message"]


def test_copilot_chat_builds_case_draft_without_persisting_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-case-draft.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Create a case draft for issue-1 and issue-2.",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["name"] == "create_case_draft"
    assert "preview only and has not been persisted" in payload["message"]
    assert "UPS recovery case (2 issues)" in payload["message"]

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            assert session.scalar(select(func.count(RecoveryCase.id))) == 0
    finally:
        engine.dispose()


def test_copilot_chat_rejects_unsupported_questions_and_logs_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-unsupported.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "What's the weather in Miami today?",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["tool_calls"] == []
    assert "grounded questions" in payload["message"]

    traces = _load_traces(database_url)
    assert len(traces) == 1
    assert traces[0].status == "unsupported"
    assert traces[0].tool_calls_json == []
