from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.common import generate_uuid, utcnow

AUDIT_EVENT_TYPE_STATUS_TRANSITION = "status_transition"
ENTITY_TYPE_ISSUE_DETECTION_RUN = "issue_detection_run"
ENTITY_TYPE_UPLOAD_JOB = "upload_job"
JOB_KIND_ISSUE_DETECTION = "issue_detection"
JOB_KIND_UPLOAD_NORMALIZATION = "upload_normalization"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_COMPLETED_WITH_ERRORS = "completed_with_errors"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status_from: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status_to: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )


class IssueDetectionRun(Base):
    __tablename__ = "issue_detection_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_duplicate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counts_by_issue_type_json: Mapped[dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
