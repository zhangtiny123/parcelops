from __future__ import annotations

from datetime import datetime
from typing import Any
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.copilot import CopilotTrace
from app.models.observability import (
    AUDIT_EVENT_TYPE_STATUS_TRANSITION,
    AuditEvent,
    IssueDetectionRun,
    JOB_KIND_ISSUE_DETECTION,
    JOB_KIND_UPLOAD_NORMALIZATION,
    JOB_STATUS_FAILED,
)
from app.models.uploads import (
    UPLOAD_STATUS_NORMALIZATION_FAILED,
    UploadJob,
    UploadNormalizationError,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class ObservabilityReferenceRead(BaseModel):
    kind: str
    id: str
    label: str
    detail: Optional[str] = None


class RecentJobRead(BaseModel):
    job_kind: str
    job_id: str
    status: str
    label: str
    detail: Optional[str] = None
    source_kind: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    normalized_row_count: Optional[int] = None
    error_count: Optional[int] = None
    created_count: Optional[int] = None
    updated_count: Optional[int] = None
    unchanged_count: Optional[int] = None
    deleted_duplicate_count: Optional[int] = None
    total_issue_count: Optional[int] = None
    counts_by_issue_type: dict[str, int] = Field(default_factory=dict)
    source_references: list[ObservabilityReferenceRead] = Field(default_factory=list)


class AdminCopilotTraceRead(BaseModel):
    id: str
    provider_name: str
    model_name: str
    status: str
    request_messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    response_text: str
    response_references: list[dict[str, Any]]
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[str] = None
    created_at: datetime


class StatusTransitionRead(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    event_type: str
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AdminObservabilityRead(BaseModel):
    recent_jobs: list[RecentJobRead]
    failed_jobs: list[RecentJobRead]
    recent_copilot_traces: list[AdminCopilotTraceRead]
    recent_status_transitions: list[StatusTransitionRead]


def _build_upload_references(
    upload_job: UploadJob,
    db: Session,
    *,
    error_limit: int = 3,
) -> list[ObservabilityReferenceRead]:
    references = [
        ObservabilityReferenceRead(
            kind="upload_job",
            id=upload_job.id,
            label=upload_job.original_filename,
            detail=upload_job.source_kind,
        )
    ]

    if upload_job.normalization_error_count <= 0 and upload_job.last_error is None:
        return references

    error_statement = (
        select(UploadNormalizationError)
        .where(UploadNormalizationError.upload_job_id == upload_job.id)
        .order_by(
            UploadNormalizationError.created_at.desc(),
            UploadNormalizationError.row_number.desc(),
        )
        .limit(error_limit)
    )
    for error in db.scalars(error_statement):
        reference_id = error.raw_row_ref or f"{upload_job.id}:row:{error.row_number}"
        references.append(
            ObservabilityReferenceRead(
                kind="raw_row_ref",
                id=reference_id,
                label=reference_id,
                detail=error.error_message,
            )
        )

    return references


def _build_upload_job_read(upload_job: UploadJob, db: Session) -> RecentJobRead:
    return RecentJobRead(
        job_kind=JOB_KIND_UPLOAD_NORMALIZATION,
        job_id=upload_job.id,
        status=upload_job.status,
        label=upload_job.original_filename,
        detail="Upload normalization job",
        source_kind=upload_job.source_kind,
        created_at=upload_job.uploaded_at,
        started_at=upload_job.normalization_started_at,
        completed_at=upload_job.normalization_completed_at,
        last_error=upload_job.last_error,
        normalized_row_count=upload_job.normalized_row_count,
        error_count=upload_job.normalization_error_count,
        source_references=_build_upload_references(upload_job, db),
    )


def _build_issue_detection_job_read(run: IssueDetectionRun) -> RecentJobRead:
    return RecentJobRead(
        job_kind=JOB_KIND_ISSUE_DETECTION,
        job_id=run.id,
        status=run.status,
        label="Issue detection run",
        detail="Recovery issue detection job",
        created_at=run.started_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        last_error=run.last_error,
        created_count=run.created_count,
        updated_count=run.updated_count,
        unchanged_count=run.unchanged_count,
        deleted_duplicate_count=run.deleted_duplicate_count,
        total_issue_count=run.total_issue_count,
        counts_by_issue_type=dict(run.counts_by_issue_type_json),
    )


def _job_sort_key(job: RecentJobRead) -> tuple[datetime, str]:
    timestamp = job.completed_at or job.started_at or job.created_at
    return (timestamp, job.job_id)


def _is_failed_upload_job(upload_job: UploadJob) -> bool:
    return (
        upload_job.status == UPLOAD_STATUS_NORMALIZATION_FAILED
        or upload_job.normalization_error_count > 0
        or upload_job.last_error is not None
    )


@router.get("/observability", response_model=AdminObservabilityRead)
def read_observability_snapshot(
    db: Annotated[Session, Depends(get_db)],
    job_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    trace_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    transition_limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminObservabilityRead:
    upload_jobs = list(
        db.scalars(
            select(UploadJob)
            .order_by(UploadJob.uploaded_at.desc(), UploadJob.id.desc())
            .limit(job_limit)
        )
    )
    issue_detection_runs = list(
        db.scalars(
            select(IssueDetectionRun)
            .order_by(IssueDetectionRun.started_at.desc(), IssueDetectionRun.id.desc())
            .limit(job_limit)
        )
    )
    failed_upload_jobs = list(
        db.scalars(
            select(UploadJob)
            .where(
                (UploadJob.status == UPLOAD_STATUS_NORMALIZATION_FAILED)
                | (UploadJob.normalization_error_count > 0)
                | (UploadJob.last_error.is_not(None))
            )
            .order_by(UploadJob.uploaded_at.desc(), UploadJob.id.desc())
            .limit(job_limit)
        )
    )
    failed_issue_detection_runs = list(
        db.scalars(
            select(IssueDetectionRun)
            .where(IssueDetectionRun.status == JOB_STATUS_FAILED)
            .order_by(IssueDetectionRun.started_at.desc(), IssueDetectionRun.id.desc())
            .limit(job_limit)
        )
    )
    recent_jobs = sorted(
        [
            *[_build_upload_job_read(upload_job, db) for upload_job in upload_jobs],
            *[_build_issue_detection_job_read(run) for run in issue_detection_runs],
        ],
        key=_job_sort_key,
        reverse=True,
    )[:job_limit]

    failed_jobs = sorted(
        [
            *[
                _build_upload_job_read(upload_job, db)
                for upload_job in failed_upload_jobs
                if _is_failed_upload_job(upload_job)
            ],
            *[
                _build_issue_detection_job_read(run)
                for run in failed_issue_detection_runs
                if run.status == JOB_STATUS_FAILED
            ],
        ],
        key=_job_sort_key,
        reverse=True,
    )[:job_limit]

    traces = list(
        db.scalars(
            select(CopilotTrace)
            .order_by(CopilotTrace.created_at.desc(), CopilotTrace.id.desc())
            .limit(trace_limit)
        )
    )
    status_transitions = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == AUDIT_EVENT_TYPE_STATUS_TRANSITION)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(transition_limit)
        )
    )

    return AdminObservabilityRead(
        recent_jobs=recent_jobs,
        failed_jobs=failed_jobs,
        recent_copilot_traces=[
            AdminCopilotTraceRead(
                id=trace.id,
                provider_name=trace.provider_name,
                model_name=trace.model_name,
                status=trace.status,
                request_messages=list(trace.request_messages_json),
                tool_calls=list(trace.tool_calls_json),
                response_text=trace.response_text,
                response_references=list(trace.response_references_json),
                latency_ms=trace.latency_ms,
                prompt_tokens=trace.prompt_tokens,
                completion_tokens=trace.completion_tokens,
                total_tokens=trace.total_tokens,
                estimated_cost_usd=(
                    str(trace.estimated_cost_usd)
                    if trace.estimated_cost_usd is not None
                    else None
                ),
                created_at=trace.created_at,
            )
            for trace in traces
        ],
        recent_status_transitions=[
            StatusTransitionRead(
                id=transition.id,
                entity_type=transition.entity_type,
                entity_id=transition.entity_id,
                event_type=transition.event_type,
                status_from=transition.status_from,
                status_to=transition.status_to,
                summary=transition.summary,
                metadata=dict(transition.metadata_json),
                created_at=transition.created_at,
            )
            for transition in status_transitions
        ],
    )
