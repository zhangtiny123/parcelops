from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.common import utcnow
from app.models.observability import (
    AUDIT_EVENT_TYPE_STATUS_TRANSITION,
    ENTITY_TYPE_ISSUE_DETECTION_RUN,
    AuditEvent,
    IssueDetectionRun,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
)


class DetectionResultLike(Protocol):
    created_count: int
    updated_count: int
    unchanged_count: int
    deleted_duplicate_count: int
    total_issue_count: int
    counts_by_issue_type: dict[str, int]


def add_audit_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    event_type: str,
    summary: str,
    status_from: str | None = None,
    status_to: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    audit_event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        summary=summary,
        status_from=status_from,
        status_to=status_to,
        metadata_json=metadata or {},
    )
    db.add(audit_event)
    return audit_event


def add_status_transition(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    status_from: str | None,
    status_to: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    return add_audit_event(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=AUDIT_EVENT_TYPE_STATUS_TRANSITION,
        summary=summary,
        status_from=status_from,
        status_to=status_to,
        metadata=metadata,
    )


def start_issue_detection_run(db: Session) -> IssueDetectionRun:
    run = IssueDetectionRun(status=JOB_STATUS_RUNNING)
    db.add(run)
    db.flush()
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_ISSUE_DETECTION_RUN,
        entity_id=run.id,
        status_from=None,
        status_to=JOB_STATUS_RUNNING,
        summary="Issue detection run started.",
    )
    return run


def complete_issue_detection_run(
    db: Session,
    *,
    run: IssueDetectionRun,
    result: DetectionResultLike,
) -> IssueDetectionRun:
    previous_status = run.status
    run.status = JOB_STATUS_COMPLETED
    run.created_count = result.created_count
    run.updated_count = result.updated_count
    run.unchanged_count = result.unchanged_count
    run.deleted_duplicate_count = result.deleted_duplicate_count
    run.total_issue_count = result.total_issue_count
    run.counts_by_issue_type_json = dict(result.counts_by_issue_type)
    run.last_error = None
    run.completed_at = utcnow()
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_ISSUE_DETECTION_RUN,
        entity_id=run.id,
        status_from=previous_status,
        status_to=run.status,
        summary="Issue detection run completed.",
        metadata={
            "created_count": run.created_count,
            "updated_count": run.updated_count,
            "unchanged_count": run.unchanged_count,
            "deleted_duplicate_count": run.deleted_duplicate_count,
            "total_issue_count": run.total_issue_count,
            "counts_by_issue_type": dict(run.counts_by_issue_type_json),
        },
    )
    return run


def fail_issue_detection_run(
    db: Session,
    *,
    run: IssueDetectionRun,
    error_message: str,
) -> IssueDetectionRun:
    previous_status = run.status
    run.status = JOB_STATUS_FAILED
    run.last_error = error_message
    run.completed_at = utcnow()
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_ISSUE_DETECTION_RUN,
        entity_id=run.id,
        status_from=previous_status,
        status_to=run.status,
        summary="Issue detection run failed.",
        metadata={"last_error": error_message},
    )
    return run
