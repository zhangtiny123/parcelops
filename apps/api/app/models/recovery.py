from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.common import generate_uuid, utcnow

RECOVERY_CASE_STATUS_OPEN = "open"
RECOVERY_CASE_STATUS_PENDING = "pending"
RECOVERY_CASE_STATUS_RESOLVED = "resolved"
RECOVERY_CASE_STATUSES = {
    RECOVERY_CASE_STATUS_OPEN,
    RECOVERY_CASE_STATUS_PENDING,
    RECOVERY_CASE_STATUS_RESOLVED,
}


class RecoveryIssue(Base):
    __tablename__ = "recovery_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    estimated_recoverable_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    shipment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("shipments.id"),
        nullable=True,
        index=True,
    )
    parcel_invoice_line_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("parcel_invoice_lines.id"),
        nullable=True,
        index=True,
    )
    three_pl_invoice_line_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("three_pl_invoice_lines.id"),
        nullable=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    issue_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    draft_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_internal_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
