from __future__ import annotations

from datetime import datetime
from typing_extensions import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.common import generate_uuid, utcnow

UPLOAD_STATUS_UPLOADED = "uploaded"
UPLOAD_STATUS_MAPPED = "mapped"
UPLOAD_STATUS_NORMALIZATION_QUEUED = "normalization_queued"
UPLOAD_STATUS_NORMALIZING = "normalizing"
UPLOAD_STATUS_NORMALIZED = "normalized"
UPLOAD_STATUS_NORMALIZED_WITH_ERRORS = "normalized_with_errors"
UPLOAD_STATUS_NORMALIZATION_FAILED = "normalization_failed"


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
    )
    file_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=UPLOAD_STATUS_UPLOADED,
        index=True,
    )
    source_kind: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    normalization_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    normalized_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    normalization_error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    normalization_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    normalization_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )


class UploadMapping(Base):
    __tablename__ = "upload_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    upload_job_id: Mapped[str] = mapped_column(
        ForeignKey("upload_jobs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    column_mappings_json: Mapped[list[dict[str, str]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class UploadNormalizationRecord(Base):
    __tablename__ = "upload_normalization_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    upload_job_id: Mapped[str] = mapped_column(
        ForeignKey("upload_jobs.id"),
        nullable=False,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    canonical_table: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    canonical_record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class UploadNormalizationError(Base):
    __tablename__ = "upload_normalization_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    upload_job_id: Mapped[str] = mapped_column(
        ForeignKey("upload_jobs.id"),
        nullable=False,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row_ref: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    row_data_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
