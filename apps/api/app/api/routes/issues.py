from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recovery import RecoveryIssue
from app.recovery_issue_detection import run_issue_detection

router = APIRouter(prefix="/issues", tags=["issues"])


class RecoveryIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_type: str
    provider_name: str
    severity: str
    status: str
    confidence: Optional[Decimal]
    estimated_recoverable_amount: Optional[Decimal]
    shipment_id: Optional[str]
    parcel_invoice_line_id: Optional[str]
    three_pl_invoice_line_id: Optional[str]
    summary: str
    evidence_json: dict[str, object]
    detected_at: datetime


class RecoveryIssueDetectionRead(BaseModel):
    created_count: int
    updated_count: int
    unchanged_count: int
    deleted_duplicate_count: int
    total_issue_count: int
    counts_by_issue_type: dict[str, int]


def _apply_issue_filters(
    statement: Select[tuple[RecoveryIssue]],
    *,
    issue_type: str | None,
    provider_name: str | None,
    severity: str | None,
    status_value: str | None,
    shipment_id: str | None,
    parcel_invoice_line_id: str | None,
    three_pl_invoice_line_id: str | None,
) -> Select[tuple[RecoveryIssue]]:
    if issue_type is not None:
        statement = statement.where(RecoveryIssue.issue_type == issue_type)
    if provider_name is not None:
        statement = statement.where(RecoveryIssue.provider_name == provider_name)
    if severity is not None:
        statement = statement.where(RecoveryIssue.severity == severity)
    if status_value is not None:
        statement = statement.where(RecoveryIssue.status == status_value)
    if shipment_id is not None:
        statement = statement.where(RecoveryIssue.shipment_id == shipment_id)
    if parcel_invoice_line_id is not None:
        statement = statement.where(
            RecoveryIssue.parcel_invoice_line_id == parcel_invoice_line_id
        )
    if three_pl_invoice_line_id is not None:
        statement = statement.where(
            RecoveryIssue.three_pl_invoice_line_id == three_pl_invoice_line_id
        )
    return statement


@router.post("/detect", response_model=RecoveryIssueDetectionRead)
def trigger_issue_detection(
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryIssueDetectionRead:
    try:
        detection_result = run_issue_detection(db)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run issue detection.",
        ) from exc

    return RecoveryIssueDetectionRead(
        created_count=detection_result.created_count,
        updated_count=detection_result.updated_count,
        unchanged_count=detection_result.unchanged_count,
        deleted_duplicate_count=detection_result.deleted_duplicate_count,
        total_issue_count=detection_result.total_issue_count,
        counts_by_issue_type=detection_result.counts_by_issue_type,
    )


@router.get("", response_model=list[RecoveryIssueRead])
def list_recovery_issues(
    db: Annotated[Session, Depends(get_db)],
    issue_type: Optional[str] = None,
    provider_name: Optional[str] = None,
    severity: Optional[str] = None,
    status_value: Annotated[Optional[str], Query(alias="status")] = None,
    shipment_id: Optional[str] = None,
    parcel_invoice_line_id: Optional[str] = None,
    three_pl_invoice_line_id: Optional[str] = None,
) -> list[RecoveryIssue]:
    statement = select(RecoveryIssue)
    statement = _apply_issue_filters(
        statement,
        issue_type=issue_type,
        provider_name=provider_name,
        severity=severity,
        status_value=status_value,
        shipment_id=shipment_id,
        parcel_invoice_line_id=parcel_invoice_line_id,
        three_pl_invoice_line_id=three_pl_invoice_line_id,
    )
    statement = statement.order_by(
        RecoveryIssue.detected_at.desc(), RecoveryIssue.id.desc()
    )
    return list(db.scalars(statement))
