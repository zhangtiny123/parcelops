from __future__ import annotations

import csv
import importlib
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import reset_database_state
from app.main import create_app
from app.models.billing import ParcelInvoiceLine, RateCardRule, ThreePLInvoiceLine
from app.models.fulfillment import OrderRecord, Shipment
from app.models.recovery import RecoveryIssue
from app.settings import reset_settings_cache
from conftest import run_migrations

REPO_ROOT = Path(__file__).resolve().parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

generate_demo_dataset = importlib.import_module("scripts.generate_demo_dataset")
generate_dataset = generate_demo_dataset.generate_dataset


def _configure_test_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_name: str,
) -> str:
    database_url = f"sqlite:///{tmp_path / database_name}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "uploads"))

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file_handle:
        return list(csv.DictReader(file_handle))


def _parse_decimal(value: str) -> Decimal | None:
    normalized = value.strip()
    if normalized == "":
        return None
    return Decimal(normalized)


def _parse_int(value: str) -> int | None:
    normalized = value.strip()
    if normalized == "":
        return None
    return int(normalized)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _seed_canonical_demo_data(database_url: str, dataset_dir: Path) -> None:
    orders = _read_csv_rows(dataset_dir / "orders.csv")
    shipments = _read_csv_rows(dataset_dir / "shipments.csv")
    parcel_invoice_lines = _read_csv_rows(dataset_dir / "parcel_invoice_lines.csv")
    three_pl_invoice_lines = _read_csv_rows(dataset_dir / "three_pl_invoice_lines.csv")
    rate_card_rules = _read_csv_rows(dataset_dir / "rate_card_rules.csv")

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            order_ids_by_external_id: dict[str, str] = {}
            for row in orders:
                order = OrderRecord(
                    external_order_id=row["external_order_id"],
                    customer_ref=row["customer_ref"],
                    order_date=_parse_datetime(row["order_date"]),
                    promised_service_level=row["promised_service_level"] or None,
                    warehouse_id=row["warehouse_id"] or None,
                )
                session.add(order)
                session.flush()
                order_ids_by_external_id[order.external_order_id] = order.id

            shipment_ids_by_external_id: dict[str, str] = {}
            shipment_ids_by_tracking_number: dict[str, str] = {}
            for row in shipments:
                shipment = Shipment(
                    external_shipment_id=row["external_shipment_id"],
                    order_id=order_ids_by_external_id.get(row["external_order_id"]),
                    tracking_number=row["tracking_number"],
                    carrier=row["carrier"],
                    service_level=row["service_level"] or None,
                    origin_zip=row["origin_zip"] or None,
                    destination_zip=row["destination_zip"] or None,
                    zone=row["zone"] or None,
                    weight_lb=_parse_decimal(row["weight_lb"]),
                    dim_weight_lb=_parse_decimal(row["dim_weight_lb"]),
                    shipped_at=_parse_datetime(row["shipped_at"]),
                    delivered_at=_parse_datetime(row["delivered_at"]),
                    warehouse_id=row["warehouse_id"] or None,
                )
                session.add(shipment)
                session.flush()
                shipment_ids_by_external_id[row["external_shipment_id"]] = shipment.id
                shipment_ids_by_tracking_number[row["tracking_number"]] = shipment.id

            for row in parcel_invoice_lines:
                session.add(
                    ParcelInvoiceLine(
                        invoice_number=row["invoice_number"],
                        invoice_date=_parse_date(row["invoice_date"]),
                        tracking_number=row["tracking_number"],
                        carrier=row["carrier"],
                        charge_type=row["charge_type"],
                        service_level_billed=row["service_level_billed"] or None,
                        billed_weight_lb=_parse_decimal(row["billed_weight_lb"]),
                        zone_billed=row["zone_billed"] or None,
                        amount=Decimal(row["amount"]),
                        currency=row["currency"],
                        shipment_id=shipment_ids_by_external_id.get(
                            row["external_shipment_id"]
                        )
                        or shipment_ids_by_tracking_number.get(row["tracking_number"]),
                        raw_row_ref=row["raw_row_ref"] or None,
                    )
                )

            for row in three_pl_invoice_lines:
                session.add(
                    ThreePLInvoiceLine(
                        invoice_number=row["invoice_number"],
                        invoice_date=_parse_date(row["invoice_date"]),
                        warehouse_id=row["warehouse_id"] or None,
                        order_id=order_ids_by_external_id.get(row["external_order_id"]),
                        sku=row["sku"] or None,
                        charge_type=row["charge_type"],
                        quantity=_parse_int(row["quantity"]),
                        unit_rate=_parse_decimal(row["unit_rate"]),
                        amount=Decimal(row["amount"]),
                        raw_row_ref=row["raw_row_ref"] or None,
                    )
                )

            for row in rate_card_rules:
                session.add(
                    RateCardRule(
                        provider_type=row["provider_type"],
                        provider_name=row["provider_name"],
                        service_level=row["service_level"] or None,
                        charge_type=row["charge_type"],
                        zone_min=_parse_int(row["zone_min"]),
                        zone_max=_parse_int(row["zone_max"]),
                        weight_min_lb=_parse_decimal(row["weight_min_lb"]),
                        weight_max_lb=_parse_decimal(row["weight_max_lb"]),
                        expected_rate=Decimal(row["expected_rate"]),
                        effective_start=(
                            _parse_date(row["effective_start"])
                            if row["effective_start"]
                            else None
                        ),
                        effective_end=(
                            _parse_date(row["effective_end"])
                            if row["effective_end"]
                            else None
                        ),
                    )
                )

            session.commit()
    finally:
        engine.dispose()


def test_issue_detection_detects_seeded_demo_anomalies_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="recovery-issue-detection.db",
    )
    dataset_dir = tmp_path / "dataset"
    generate_dataset(dataset_dir)
    _seed_canonical_demo_data(database_url, dataset_dir)

    expected_counts = {
        "billed_weight_mismatch": 4,
        "duplicate_charge": 4,
        "incorrect_unit_rate_vs_rate_card": 3,
        "invoice_line_without_matched_order_or_shipment": 2,
        "invoice_line_without_matched_shipment": 2,
        "zone_mismatch": 3,
    }

    with TestClient(create_app()) as client:
        first_detection_response = client.post("/issues/detect")
        second_detection_response = client.post("/issues/detect")
        issues_response = client.get("/issues")

    assert first_detection_response.status_code == 200
    first_detection = first_detection_response.json()
    assert first_detection["created_count"] == 18
    assert first_detection["updated_count"] == 0
    assert first_detection["unchanged_count"] == 0
    assert first_detection["deleted_duplicate_count"] == 0
    assert first_detection["total_issue_count"] == 18
    assert first_detection["counts_by_issue_type"] == expected_counts

    assert second_detection_response.status_code == 200
    second_detection = second_detection_response.json()
    assert second_detection["created_count"] == 0
    assert second_detection["updated_count"] == 0
    assert second_detection["unchanged_count"] == 18
    assert second_detection["deleted_duplicate_count"] == 0
    assert second_detection["total_issue_count"] == 18
    assert second_detection["counts_by_issue_type"] == expected_counts

    assert issues_response.status_code == 200
    issues = issues_response.json()
    assert len(issues) == 18

    issue_counts: dict[str, int] = {}
    for issue in issues:
        issue_counts[issue["issue_type"]] = issue_counts.get(issue["issue_type"], 0) + 1

    assert issue_counts == expected_counts


def test_issue_list_supports_basic_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="recovery-issue-filters.db",
    )

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    RecoveryIssue(
                        issue_type="duplicate_charge",
                        provider_name="UPS",
                        severity="high",
                        status="open",
                        confidence=Decimal("0.9900"),
                        estimated_recoverable_amount=Decimal("14.10"),
                        shipment_id="ship-1",
                        parcel_invoice_line_id="parcel-1",
                        three_pl_invoice_line_id=None,
                        summary="Duplicate UPS charge.",
                        evidence_json={"tracking_number": "1Z123"},
                        detected_at=datetime(2026, 3, 23, 12, 0, tzinfo=timezone.utc),
                    ),
                    RecoveryIssue(
                        issue_type="zone_mismatch",
                        provider_name="FedEx",
                        severity="medium",
                        status="open",
                        confidence=Decimal("0.9700"),
                        estimated_recoverable_amount=Decimal("8.25"),
                        shipment_id="ship-2",
                        parcel_invoice_line_id="parcel-2",
                        three_pl_invoice_line_id=None,
                        summary="FedEx zone mismatch.",
                        evidence_json={"tracking_number": "790000000001"},
                        detected_at=datetime(2026, 3, 23, 11, 0, tzinfo=timezone.utc),
                    ),
                    RecoveryIssue(
                        issue_type="incorrect_unit_rate_vs_rate_card",
                        provider_name="FlexFulfill 3PL",
                        severity="high",
                        status="resolved",
                        confidence=Decimal("0.9800"),
                        estimated_recoverable_amount=Decimal("0.75"),
                        shipment_id=None,
                        parcel_invoice_line_id=None,
                        three_pl_invoice_line_id="tpl-1",
                        summary="3PL pick fee rate mismatch.",
                        evidence_json={"invoice_number": "3PL-1"},
                        detected_at=datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc),
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()

    with TestClient(create_app()) as client:
        issue_type_response = client.get(
            "/issues", params={"issue_type": "duplicate_charge"}
        )
        status_response = client.get("/issues", params={"status": "open"})
        provider_response = client.get(
            "/issues", params={"provider_name": "FlexFulfill 3PL"}
        )
        shipment_response = client.get("/issues", params={"shipment_id": "ship-2"})

    assert issue_type_response.status_code == 200
    issue_type_issues = issue_type_response.json()
    assert len(issue_type_issues) == 1
    assert issue_type_issues[0]["issue_type"] == "duplicate_charge"

    assert status_response.status_code == 200
    status_issues = status_response.json()
    assert len(status_issues) == 2
    assert {issue["status"] for issue in status_issues} == {"open"}

    assert provider_response.status_code == 200
    provider_issues = provider_response.json()
    assert len(provider_issues) == 1
    assert provider_issues[0]["provider_name"] == "FlexFulfill 3PL"

    assert shipment_response.status_code == 200
    shipment_issues = shipment_response.json()
    assert len(shipment_issues) == 1
    assert shipment_issues[0]["shipment_id"] == "ship-2"
