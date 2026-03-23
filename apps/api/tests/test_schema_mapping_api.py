from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import reset_database_state
from app.main import create_app
from app.models.uploads import UploadJob, UploadMapping
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
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "uploads"))

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def _create_inline_string_cell(reference: str, value: str) -> str:
    return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'


def _build_xlsx_bytes(rows: list[list[str]]) -> bytes:
    worksheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _create_inline_string_cell(f"{chr(64 + column_index)}{row_index}", value)
            for column_index, value in enumerate(row, start=1)
        )
        worksheet_rows.append(f'<row r="{row_index}">{cells}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f"{''.join(worksheet_rows)}"
        "</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="Sheet1" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_rels_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    return buffer.getvalue()


def test_preview_returns_csv_rows_and_infers_source_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(tmp_path, monkeypatch, database_name="preview-csv.db")

    payload = (
        "external_order_id,customer_ref,order_date,promised_service_level,warehouse_id\n"
        "ORD-1,CUST-1,2026-03-01T12:00:00Z,Ground,WH-1\n"
    ).encode("utf-8")

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={"file": ("mystery.csv", payload, "text/csv")},
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        preview_response = client.get(f"/uploads/{upload_id}/preview")

    assert preview_response.status_code == 200
    body = preview_response.json()
    assert body["columns"] == [
        "external_order_id",
        "customer_ref",
        "order_date",
        "promised_service_level",
        "warehouse_id",
    ]
    assert body["rows"][0]["external_order_id"] == "ORD-1"
    assert body["rows"][0]["warehouse_id"] == "WH-1"
    assert body["preview_row_count"] == 1
    assert body["inferred_source_kind"] == "order"
    assert "order" in body["supported_source_kinds"]


def test_preview_supports_xlsx_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(tmp_path, monkeypatch, database_name="preview-xlsx.db")

    payload = _build_xlsx_bytes(
        [
            [
                "external_shipment_id",
                "tracking_number",
                "event_type",
                "event_time",
                "location",
            ],
            [
                "SHP-1",
                "1Z123",
                "Delivered",
                "2026-03-02T10:00:00Z",
                "New York, NY",
            ],
        ]
    )

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={
                "file": (
                    "spreadsheet.xlsx",
                    payload,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        preview_response = client.get(f"/uploads/{upload_id}/preview")

    assert preview_response.status_code == 200
    body = preview_response.json()
    assert body["columns"] == [
        "external_shipment_id",
        "tracking_number",
        "event_type",
        "event_time",
        "location",
    ]
    assert body["rows"][0]["event_type"] == "Delivered"
    assert body["inferred_source_kind"] == "shipment_event"


def test_suggested_mapping_returns_known_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(tmp_path, monkeypatch, database_name="suggest.db")

    payload = (
        "invoice_number,invoice_date,tracking_number,carrier,charge_type,amount,currency\n"
        "INV-1,2026-03-05,1Z123,UPS,transportation,14.10,USD\n"
    ).encode("utf-8")

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={"file": ("unknown.csv", payload, "text/csv")},
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        suggestion_response = client.get(f"/uploads/{upload_id}/suggested-mapping")

    assert suggestion_response.status_code == 200
    body = suggestion_response.json()
    assert body["source_kind"] == "parcel_invoice"
    assert body["inferred_source_kind"] == "parcel_invoice"
    suggested_mappings = {
        item["source_column"]: item["canonical_field"]
        for item in body["suggested_mappings"]
    }
    assert suggested_mappings["invoice_number"] == "invoice_number"
    assert suggested_mappings["tracking_number"] == "tracking_number"
    assert suggested_mappings["amount"] == "amount"
    assert any(field["name"] == "invoice_number" for field in body["canonical_fields"])
    assert body["saved_mapping"] is None


def test_save_mapping_persists_custom_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="mapping-save.db",
    )

    payload = (
        "Order ID,Customer Ref,Order Date\nORD-2,CUST-2,2026-03-06T09:00:00Z\n"
    ).encode("utf-8")

    with TestClient(create_app()) as client:
        upload_response = client.post(
            "/uploads",
            files={"file": ("custom.csv", payload, "text/csv")},
        )
        assert upload_response.status_code == 201
        upload_id = upload_response.json()["id"]

        save_response = client.put(
            f"/uploads/{upload_id}/mapping",
            json={
                "source_kind": "order",
                "mappings": [
                    {
                        "source_column": "Order ID",
                        "canonical_field": "external_order_id",
                    },
                    {
                        "source_column": "Customer Ref",
                        "canonical_field": "customer_ref",
                    },
                    {
                        "source_column": "Order Date",
                        "canonical_field": "order_date",
                    },
                ],
            },
        )
        detail_response = client.get(f"/uploads/{upload_id}/mapping")
        suggestion_response = client.get(f"/uploads/{upload_id}/suggested-mapping")

    assert save_response.status_code == 200
    assert detail_response.status_code == 200
    assert suggestion_response.status_code == 200

    saved_mapping = detail_response.json()
    assert saved_mapping["source_kind"] == "order"
    assert saved_mapping["mappings"] == [
        {"source_column": "Order ID", "canonical_field": "external_order_id"},
        {"source_column": "Customer Ref", "canonical_field": "customer_ref"},
        {"source_column": "Order Date", "canonical_field": "order_date"},
    ]
    assert suggestion_response.json()["saved_mapping"]["id"] == saved_mapping["id"]

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            upload_job = session.get(UploadJob, upload_id)
            upload_mapping = session.scalar(
                select(UploadMapping).where(UploadMapping.upload_job_id == upload_id)
            )
            assert upload_job is not None
            assert upload_job.source_kind == "order"
            assert upload_mapping is not None
            assert upload_mapping.source_kind == "order"
            assert upload_mapping.column_mappings_json == saved_mapping["mappings"]
    finally:
        engine.dispose()
