from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import reset_database_state
from app.main import create_app
from app.models.recovery import RecoveryIssue
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

    reset_settings_cache()
    reset_database_state()
    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    return database_url


def _seed_recovery_issues(database_url: str) -> list[RecoveryIssue]:
    issues = [
        RecoveryIssue(
            id="issue-1",
            issue_type="billed_weight_mismatch",
            provider_name="UPS",
            severity="high",
            status="open",
            confidence=Decimal("0.9300"),
            estimated_recoverable_amount=Decimal("12.50"),
            shipment_id="shipment-1",
            summary="Billed weight exceeds the modeled shipment weight.",
            evidence_json={"invoice_number": "INV-1001", "tracking_number": "1Z999"},
            detected_at=datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc),
        ),
        RecoveryIssue(
            id="issue-2",
            issue_type="duplicate_charge",
            provider_name="UPS",
            severity="medium",
            status="open",
            confidence=Decimal("0.8800"),
            estimated_recoverable_amount=Decimal("6.25"),
            parcel_invoice_line_id="parcel-line-2",
            summary="The same parcel line appears to have been billed twice.",
            evidence_json={"invoice_number": "INV-1002", "duplicate_count": 2},
            detected_at=datetime(2026, 3, 21, 9, 15, tzinfo=timezone.utc),
        ),
    ]

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            session.add_all(issues)
            session.commit()
    finally:
        engine.dispose()

    return issues


def test_recovery_case_workflow_supports_create_list_detail_and_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="recovery-case-workflow.db",
    )
    _seed_recovery_issues(database_url)

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/cases",
            json={"issue_ids": ["issue-2", "issue-1"]},
        )

        assert create_response.status_code == 201
        created_case = create_response.json()
        case_id = created_case["id"]

        assert created_case["status"] == "open"
        assert created_case["issue_ids"] == ["issue-2", "issue-1"]
        assert created_case["issue_count"] == 2
        assert created_case["estimated_recoverable_amount"] == "18.75"
        assert created_case["title"] == "UPS recovery case (2 issues)"
        assert created_case["draft_summary"]
        assert "18.75" in created_case["draft_summary"]
        assert "issue-2" in created_case["draft_summary"]
        assert "INV-1002" in created_case["draft_summary"]
        assert "1Z999" in created_case["draft_summary"]
        assert created_case["draft_email"]
        assert "UPS recovery case (2 issues)" in created_case["draft_email"]
        assert "INV-1001" in created_case["draft_email"]
        assert created_case["draft_internal_note"]
        assert "issue-1" in created_case["draft_internal_note"]
        assert "Tracking Number: 1Z999" in created_case["draft_internal_note"]
        assert [issue["id"] for issue in created_case["issues"]] == [
            "issue-2",
            "issue-1",
        ]

        list_response = client.get("/cases")
        detail_response = client.get(f"/cases/{case_id}")

        assert list_response.status_code == 200
        listed_cases = list_response.json()
        assert len(listed_cases) == 1
        assert listed_cases[0]["id"] == case_id
        assert listed_cases[0]["issue_count"] == 2
        assert listed_cases[0]["estimated_recoverable_amount"] == "18.75"
        assert listed_cases[0]["draft_internal_note"]

        assert detail_response.status_code == 200
        detailed_case = detail_response.json()
        assert detailed_case["id"] == case_id
        assert detailed_case["issues"][0]["summary"].startswith(
            "The same parcel line appears",
        )

        update_response = client.put(
            f"/cases/{case_id}",
            json={
                "title": "UPS March disputes",
                "status": "pending",
                "draft_summary": "Updated summary for operator review.",
                "draft_email": "Updated dispute email draft.",
                "draft_internal_note": "Updated internal next-step note.",
            },
        )

        assert update_response.status_code == 200
        updated_case = update_response.json()
        assert updated_case["title"] == "UPS March disputes"
        assert updated_case["status"] == "pending"
        assert updated_case["draft_summary"] == "Updated summary for operator review."
        assert updated_case["draft_email"] == "Updated dispute email draft."
        assert updated_case["draft_internal_note"] == "Updated internal next-step note."

        persisted_detail_response = client.get(f"/cases/{case_id}")

    assert persisted_detail_response.status_code == 200
    persisted_case = persisted_detail_response.json()
    assert persisted_case["title"] == "UPS March disputes"
    assert persisted_case["status"] == "pending"
    assert persisted_case["draft_summary"] == "Updated summary for operator review."
    assert persisted_case["draft_email"] == "Updated dispute email draft."
    assert persisted_case["draft_internal_note"] == "Updated internal next-step note."


def test_recovery_case_workflow_can_regenerate_drafts_from_linked_issue_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="recovery-case-regenerate.db",
    )
    _seed_recovery_issues(database_url)

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/cases", json={"issue_ids": ["issue-1", "issue-2"]}
        )
        case_id = create_response.json()["id"]

        update_response = client.put(
            f"/cases/{case_id}",
            json={
                "title": "Operator-edited title",
                "status": "pending",
                "draft_summary": "Manually edited summary.",
                "draft_email": "Manually edited email.",
                "draft_internal_note": "Manually edited internal note.",
            },
        )

        regenerate_response = client.post(
            f"/cases/{case_id}/drafts/regenerate",
            json={"title": "UPS April disputes"},
        )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert regenerate_response.status_code == 200

    regenerated_case = regenerate_response.json()
    assert regenerated_case["title"] == "UPS April disputes"
    assert regenerated_case["status"] == "pending"
    assert "Manually edited summary." not in regenerated_case["draft_summary"]
    assert "Manually edited email." not in regenerated_case["draft_email"]
    assert (
        "Manually edited internal note." not in regenerated_case["draft_internal_note"]
    )
    assert "INV-1001" in regenerated_case["draft_email"]
    assert "issue-2" in regenerated_case["draft_internal_note"]


def test_recovery_case_workflow_rejects_invalid_issue_selection_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _configure_test_environment(
        tmp_path,
        monkeypatch,
        database_name="recovery-case-validation.db",
    )
    _seed_recovery_issues(database_url)

    with TestClient(create_app()) as client:
        missing_issue_response = client.post(
            "/cases",
            json={"issue_ids": ["missing-issue"]},
        )
        empty_issue_response = client.post("/cases", json={"issue_ids": []})
        create_response = client.post("/cases", json={"issue_ids": ["issue-1"]})

        assert missing_issue_response.status_code == 400
        assert "Recovery issues not found" in missing_issue_response.json()["detail"]

        assert empty_issue_response.status_code == 400
        assert "At least one recovery issue" in empty_issue_response.json()["detail"]

        case_id = create_response.json()["id"]
        invalid_status_response = client.put(
            f"/cases/{case_id}",
            json={
                "title": "UPS single issue case",
                "status": "closed",
                "draft_summary": "Summary",
                "draft_email": "Email",
                "draft_internal_note": "Internal note",
            },
        )

    assert create_response.status_code == 201
    assert invalid_status_response.status_code == 400
    assert "open, pending, or resolved" in invalid_status_response.json()["detail"]
