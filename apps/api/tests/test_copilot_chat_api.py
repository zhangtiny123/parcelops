from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.copilot.eval_fixture import seed_copilot_eval_records
from app.db.session import reset_database_state
from app.main import create_app
from app.models.copilot import CopilotTrace
from app.models.recovery import RecoveryCase
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
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            seed_copilot_eval_records(session)
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


def test_copilot_chat_counts_recovery_issues_without_listing_top_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-issue-count.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "How many recovery issues do we have?",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["name"] == "search_issues"
    assert payload["tool_calls"][0]["arguments"]["intent"] == "count"
    assert payload["message"] == "ParcelOps currently has 3 recovery issue(s)."
    assert payload["references"] == []


def test_copilot_chat_counts_shipment_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-shipment-count.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "How many shipment records do we have?",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["name"] == "search_shipments"
    assert payload["tool_calls"][0]["arguments"]["intent"] == "count"
    assert payload["message"] == "ParcelOps currently has 1 shipment record(s)."
    assert payload["references"] == []


def test_copilot_chat_formats_high_confidence_issue_questions_distinctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="copilot-high-confidence.db",
    )
    _seed_copilot_records(database_url)

    with TestClient(create_app()) as client:
        response = client.post(
            "/copilot/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Show the billing errors with the strongest confidence and the evidence behind them.",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["name"] == "search_issues"
    assert payload["tool_calls"][0]["arguments"]["intent"] == "high_confidence"
    assert "high-confidence recovery issue(s)" in payload["message"]
    assert payload["references"][0]["id"] == "issue-1"


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
    assert "Internal next-step note" in payload["message"]
    assert "INV-1001" in payload["message"]

    traces = _load_traces(database_url)
    assert len(traces) == 1
    tool_output = traces[0].tool_calls_json[0]["output"]
    assert tool_output["draft_internal_note"].startswith("Internal next-step note")
    assert "INV-1001" in tool_output["draft_summary"]
    assert "INV-1001" in tool_output["draft_email"]

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
