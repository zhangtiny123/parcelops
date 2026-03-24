from __future__ import annotations

from pathlib import Path
from typing import Type

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base_class import Base
from app.db.session import reset_database_state
from app.main import create_app
from app.models.billing import ParcelInvoiceLine, RateCardRule, ThreePLInvoiceLine
from app.models.fulfillment import OrderRecord, Shipment, ShipmentEvent
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
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "uploads"))

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


@pytest.mark.parametrize(
    ("source_kind", "payload", "mappings", "model"),
    [
        (
            "order",
            (
                "Order ID,Customer Ref,Order Date,Promised Service Level,Warehouse\n"
                "ORD-100,CUST-100,2026-03-10T09:00:00Z,Ground,WH-1\n"
            ),
            [
                {"source_column": "Order ID", "canonical_field": "external_order_id"},
                {"source_column": "Customer Ref", "canonical_field": "customer_ref"},
                {"source_column": "Order Date", "canonical_field": "order_date"},
                {
                    "source_column": "Promised Service Level",
                    "canonical_field": "promised_service_level",
                },
                {"source_column": "Warehouse", "canonical_field": "warehouse_id"},
            ],
            OrderRecord,
        ),
        (
            "shipment",
            (
                "Shipment ID,Order ID,Tracking,Carrier,Service,Origin ZIP,Destination ZIP\n"
                "SHP-100,ORD-100,1ZTRACK100,UPS,Ground,60601,10001\n"
            ),
            [
                {
                    "source_column": "Shipment ID",
                    "canonical_field": "external_shipment_id",
                },
                {"source_column": "Order ID", "canonical_field": "external_order_id"},
                {"source_column": "Tracking", "canonical_field": "tracking_number"},
                {"source_column": "Carrier", "canonical_field": "carrier"},
                {"source_column": "Service", "canonical_field": "service_level"},
                {"source_column": "Origin ZIP", "canonical_field": "origin_zip"},
                {
                    "source_column": "Destination ZIP",
                    "canonical_field": "destination_zip",
                },
            ],
            Shipment,
        ),
        (
            "shipment_event",
            (
                "Tracking,Event,Event Date,Location,Row Reference\n"
                "1ZTRACK100,Delivered,2026-03-10T13:00:00Z,New York,EVT-100\n"
            ),
            [
                {"source_column": "Tracking", "canonical_field": "tracking_number"},
                {"source_column": "Event", "canonical_field": "event_type"},
                {"source_column": "Event Date", "canonical_field": "event_time"},
                {"source_column": "Location", "canonical_field": "location"},
                {"source_column": "Row Reference", "canonical_field": "raw_row_ref"},
            ],
            ShipmentEvent,
        ),
        (
            "parcel_invoice",
            (
                "Invoice Number,Invoice Date,Tracking,Carrier,Charge Type,Amount,Raw Row Ref\n"
                "INV-100,2026-03-10,1ZTRACK100,UPS,transportation,14.10,PAR-100\n"
            ),
            [
                {
                    "source_column": "Invoice Number",
                    "canonical_field": "invoice_number",
                },
                {"source_column": "Invoice Date", "canonical_field": "invoice_date"},
                {"source_column": "Tracking", "canonical_field": "tracking_number"},
                {"source_column": "Carrier", "canonical_field": "carrier"},
                {"source_column": "Charge Type", "canonical_field": "charge_type"},
                {"source_column": "Amount", "canonical_field": "amount"},
                {"source_column": "Raw Row Ref", "canonical_field": "raw_row_ref"},
            ],
            ParcelInvoiceLine,
        ),
        (
            "three_pl_invoice",
            (
                "Invoice Number,Invoice Date,Warehouse,Order ID,Charge Type,Quantity,Amount,Raw Row Ref\n"
                "TPL-100,2026-03-10,WH-1,ORD-100,pick_fee,1,2.10,TPL-ROW-100\n"
            ),
            [
                {
                    "source_column": "Invoice Number",
                    "canonical_field": "invoice_number",
                },
                {"source_column": "Invoice Date", "canonical_field": "invoice_date"},
                {"source_column": "Warehouse", "canonical_field": "warehouse_id"},
                {"source_column": "Order ID", "canonical_field": "external_order_id"},
                {"source_column": "Charge Type", "canonical_field": "charge_type"},
                {"source_column": "Quantity", "canonical_field": "quantity"},
                {"source_column": "Amount", "canonical_field": "amount"},
                {"source_column": "Raw Row Ref", "canonical_field": "raw_row_ref"},
            ],
            ThreePLInvoiceLine,
        ),
        (
            "rate_card",
            (
                "Provider Type,Provider Name,Service Level,Charge Type,Expected Rate,Effective Start\n"
                "parcel,UPS,Ground,transportation,11.25,2026-01-01\n"
            ),
            [
                {
                    "source_column": "Provider Type",
                    "canonical_field": "provider_type",
                },
                {
                    "source_column": "Provider Name",
                    "canonical_field": "provider_name",
                },
                {
                    "source_column": "Service Level",
                    "canonical_field": "service_level",
                },
                {"source_column": "Charge Type", "canonical_field": "charge_type"},
                {
                    "source_column": "Expected Rate",
                    "canonical_field": "expected_rate",
                },
                {
                    "source_column": "Effective Start",
                    "canonical_field": "effective_start",
                },
            ],
            RateCardRule,
        ),
    ],
)
def test_normalization_inserts_canonical_rows_for_supported_source_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: str,
    payload: str,
    mappings: list[dict[str, str]],
    model: Type[Base],
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name=f"{source_kind}.db",
    )

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={"file": ("input.csv", payload.encode("utf-8"), "text/csv")},
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        mapping_response = client.put(
            f"/uploads/{upload_id}/mapping",
            json={"source_kind": source_kind, "mappings": mappings},
        )
        normalize_response = client.post(f"/uploads/{upload_id}/normalize")
        records_response = client.get(f"/uploads/{upload_id}/normalization-records")
        errors_response = client.get(f"/uploads/{upload_id}/normalization-errors")

    assert mapping_response.status_code == 200
    assert normalize_response.status_code == 200
    body = normalize_response.json()
    assert body["status"] == "normalized"
    assert body["normalization_task_id"]
    assert body["normalized_row_count"] == 1
    assert body["normalization_error_count"] == 0
    assert body["normalization_started_at"] is not None
    assert body["normalization_completed_at"] is not None
    assert body["last_error"] is None

    assert errors_response.status_code == 200
    assert errors_response.json() == []

    assert records_response.status_code == 200
    records = records_response.json()
    assert len(records) == 1
    assert records[0]["source_kind"] == source_kind
    assert records[0]["canonical_table"] == model.__tablename__
    assert records[0]["raw_row_ref"]

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            assert len(list(session.scalars(select(model)))) == 1
    finally:
        engine.dispose()


def test_normalization_captures_partial_row_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="partial-errors.db",
    )

    payload = (
        "Tracking,Event,Event Date,Location,Row Reference\n"
        "1ZTRACK100,Delivered,2026-03-10T13:00:00Z,New York,EVT-100\n"
        "1ZTRACK101,Delayed,not-a-date,Boston,EVT-101\n"
    ).encode("utf-8")

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={"file": ("events.csv", payload, "text/csv")},
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        mapping_response = client.put(
            f"/uploads/{upload_id}/mapping",
            json={
                "source_kind": "shipment_event",
                "mappings": [
                    {
                        "source_column": "Tracking",
                        "canonical_field": "tracking_number",
                    },
                    {"source_column": "Event", "canonical_field": "event_type"},
                    {"source_column": "Event Date", "canonical_field": "event_time"},
                    {"source_column": "Location", "canonical_field": "location"},
                    {
                        "source_column": "Row Reference",
                        "canonical_field": "raw_row_ref",
                    },
                ],
            },
        )
        normalize_response = client.post(f"/uploads/{upload_id}/normalize")
        errors_response = client.get(f"/uploads/{upload_id}/normalization-errors")
        records_response = client.get(f"/uploads/{upload_id}/normalization-records")

    assert mapping_response.status_code == 200
    assert normalize_response.status_code == 200
    body = normalize_response.json()
    assert body["status"] == "normalized_with_errors"
    assert body["normalized_row_count"] == 1
    assert body["normalization_error_count"] == 1

    assert records_response.status_code == 200
    records = records_response.json()
    assert len(records) == 1
    assert records[0]["raw_row_ref"] == "EVT-100"

    assert errors_response.status_code == 200
    errors = errors_response.json()
    assert len(errors) == 1
    assert errors[0]["row_number"] == 3
    assert errors[0]["raw_row_ref"] == "EVT-101"
    assert errors[0]["error_message"] == (
        "Invalid datetime value for event_time: not-a-date"
    )
    assert errors[0]["row_data"]["Row Reference"] == "EVT-101"

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            assert len(list(session.scalars(select(ShipmentEvent)))) == 1
    finally:
        engine.dispose()
