from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import reset_database_state
from app.main import create_app
from app.models.uploads import UploadJob
from app.settings import reset_settings_cache
from conftest import run_migrations


def _configure_test_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_name: str,
    max_upload_size_bytes: int | None = None,
) -> str:
    database_url = f"sqlite:///{tmp_path / database_name}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "uploads"))
    if max_upload_size_bytes is not None:
        monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", str(max_upload_size_bytes))

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def _get_upload_count(database_url: str) -> int:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            return len(list(session.scalars(select(UploadJob))))
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    (
        "filename",
        "content_type",
        "payload",
        "expected_file_type",
        "expected_source_kind",
    ),
    [
        (
            "parcel_invoice_lines.csv",
            "text/csv",
            b"invoice_number,tracking_number\nINV-1,TRACK-1\n",
            "csv",
            "parcel_invoice",
        ),
        (
            "rate_card_rules.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"placeholder-xlsx-content",
            "xlsx",
            "rate_card",
        ),
    ],
)
def test_upload_persists_supported_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    payload: bytes,
    expected_file_type: str,
    expected_source_kind: str,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name=f"{expected_file_type}.db",
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/uploads",
            files={"file": (filename, payload, content_type)},
        )

    assert response.status_code == 201
    body = response.json()
    upload_id = body["id"]
    assert body["original_filename"] == filename
    assert body["file_type"] == expected_file_type
    assert body["file_size_bytes"] == len(payload)
    assert body["status"] == "uploaded"
    assert body["source_kind"] == expected_source_kind
    assert body["uploaded_at"]

    stored_path = tmp_path / "uploads" / upload_id / filename
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            upload_job = session.get(UploadJob, upload_id)
            assert upload_job is not None
            assert upload_job.storage_key == f"{upload_id}/{filename}"
    finally:
        engine.dispose()


def test_upload_list_and_detail_endpoints_return_saved_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(tmp_path, monkeypatch, database_name="detail.db")

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/uploads",
            files={
                "file": ("shipment_events.csv", b"id,event\n1,Delivered\n", "text/csv")
            },
        )
        assert create_response.status_code == 201
        upload_id = create_response.json()["id"]

        detail_response = client.get(f"/uploads/{upload_id}")
        list_response = client.get("/uploads")

    assert detail_response.status_code == 200
    assert list_response.status_code == 200
    assert detail_response.json()["id"] == upload_id
    assert detail_response.json()["source_kind"] == "shipment_event"
    assert [item["id"] for item in list_response.json()] == [upload_id]


def test_upload_rejects_unsupported_file_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="unsupported.db",
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/uploads",
            files={"file": ("notes.txt", b"not-supported", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "Unsupported file type. Only .csv and .xlsx uploads are supported."
    )
    assert _get_upload_count(database_url) == 0
    assert not (tmp_path / "uploads").exists()


def test_upload_rejects_files_over_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="too-large.db",
        max_upload_size_bytes=4,
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/uploads",
            files={"file": ("orders.csv", b"12345", "text/csv")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file exceeds the 4-byte limit."
    assert _get_upload_count(database_url) == 0
    uploads_root = tmp_path / "uploads"
    assert not uploads_root.exists() or not any(uploads_root.rglob("*"))
