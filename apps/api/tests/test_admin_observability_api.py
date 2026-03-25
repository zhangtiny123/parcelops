from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import app.api.routes.issues as issues_routes
from app.db.session import reset_database_state
from app.main import create_app
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
    monkeypatch.setenv("COPILOT_PROVIDER", "heuristic")

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def test_admin_observability_snapshot_exposes_jobs_failures_traces_and_transitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="admin-observability.db",
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
        detect_response = client.post("/issues/detect")
        copilot_response = client.post(
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
        observability_response = client.get("/admin/observability")

    assert mapping_response.status_code == 200
    assert normalize_response.status_code == 200
    assert normalize_response.json()["status"] == "normalized_with_errors"
    assert detect_response.status_code == 200
    detect_run_id = detect_response.json()["run_id"]
    assert copilot_response.status_code == 200
    assert copilot_response.json()["status"] == "unsupported"
    assert observability_response.status_code == 200

    snapshot = observability_response.json()

    upload_job = next(
        job
        for job in snapshot["recent_jobs"]
        if job["job_kind"] == "upload_normalization" and job["job_id"] == upload_id
    )
    assert upload_job["status"] == "normalized_with_errors"
    assert upload_job["error_count"] == 1

    detection_job = next(
        job
        for job in snapshot["recent_jobs"]
        if job["job_kind"] == "issue_detection" and job["job_id"] == detect_run_id
    )
    assert detection_job["status"] == "completed"
    assert detection_job["total_issue_count"] == 0

    failed_upload_job = next(
        job
        for job in snapshot["failed_jobs"]
        if job["job_kind"] == "upload_normalization" and job["job_id"] == upload_id
    )
    assert failed_upload_job["status"] == "normalized_with_errors"
    assert failed_upload_job["source_references"][0]["id"] == upload_id
    assert any(
        reference["id"] == "EVT-101"
        for reference in failed_upload_job["source_references"]
    )

    trace = snapshot["recent_copilot_traces"][0]
    assert trace["status"] == "unsupported"
    assert (
        trace["request_messages"][0]["content"] == "What's the weather in Miami today?"
    )
    assert trace["tool_calls"] == []

    assert any(
        transition["entity_type"] == "upload_job"
        and transition["entity_id"] == upload_id
        and transition["status_to"] == "normalizing"
        for transition in snapshot["recent_status_transitions"]
    )
    assert any(
        transition["entity_type"] == "issue_detection_run"
        and transition["entity_id"] == detect_run_id
        and transition["status_to"] == "completed"
        for transition in snapshot["recent_status_transitions"]
    )


def test_admin_observability_snapshot_exposes_failed_issue_detection_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="admin-observability-failure.db",
    )

    def _raise_detection_failure(*_: object) -> None:
        raise RuntimeError("simulated detection failure")

    monkeypatch.setattr(
        issues_routes,
        "run_issue_detection",
        _raise_detection_failure,
    )

    with TestClient(create_app()) as client:
        detect_response = client.post("/issues/detect")
        observability_response = client.get("/admin/observability")

    assert detect_response.status_code == 500
    assert detect_response.json() == {"detail": "Failed to run issue detection."}
    assert observability_response.status_code == 200

    snapshot = observability_response.json()
    failed_run = next(
        job for job in snapshot["failed_jobs"] if job["job_kind"] == "issue_detection"
    )
    assert failed_run["status"] == "failed"
    assert failed_run["last_error"] == "simulated detection failure"

    assert any(
        transition["entity_type"] == "issue_detection_run"
        and transition["entity_id"] == failed_run["job_id"]
        and transition["status_to"] == "failed"
        for transition in snapshot["recent_status_transitions"]
    )
