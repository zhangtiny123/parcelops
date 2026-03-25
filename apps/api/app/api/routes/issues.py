from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.issue_dashboard import get_issue_dashboard_summary, list_high_severity_issues
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


class RecoveryIssueTypeMetricRead(BaseModel):
    issue_type: str
    count: int
    estimated_recoverable_amount: Decimal


class RecoveryIssueProviderMetricRead(BaseModel):
    provider_name: str
    count: int
    estimated_recoverable_amount: Decimal


class RecoveryIssueTrendPointRead(BaseModel):
    date: date
    count: int
    estimated_recoverable_amount: Decimal


class RecoveryIssueDashboardRead(BaseModel):
    total_issue_count: int
    total_recoverable_amount: Decimal
    issues_by_type: list[RecoveryIssueTypeMetricRead]
    issues_by_provider: list[RecoveryIssueProviderMetricRead]
    trend: list[RecoveryIssueTrendPointRead]


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


@router.get("/dashboard", response_model=RecoveryIssueDashboardRead)
def read_issue_dashboard(
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> RecoveryIssueDashboardRead:
    dashboard = get_issue_dashboard_summary(db, trend_days=days)
    return RecoveryIssueDashboardRead(
        total_issue_count=dashboard.total_issue_count,
        total_recoverable_amount=dashboard.total_recoverable_amount,
        issues_by_type=[
            RecoveryIssueTypeMetricRead(
                issue_type=metric.name,
                count=metric.count,
                estimated_recoverable_amount=metric.estimated_recoverable_amount,
            )
            for metric in dashboard.issues_by_type
        ],
        issues_by_provider=[
            RecoveryIssueProviderMetricRead(
                provider_name=metric.name,
                count=metric.count,
                estimated_recoverable_amount=metric.estimated_recoverable_amount,
            )
            for metric in dashboard.issues_by_provider
        ],
        trend=[
            RecoveryIssueTrendPointRead(
                date=point.date,
                count=point.count,
                estimated_recoverable_amount=point.estimated_recoverable_amount,
            )
            for point in dashboard.trend
        ],
    )


@router.get("/high-severity", response_model=list[RecoveryIssueRead])
def list_top_high_severity_issues(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[RecoveryIssue]:
    return list_high_severity_issues(db, limit=limit)


@router.get("/{issue_id}", response_model=RecoveryIssueRead)
def read_recovery_issue(
    issue_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryIssue:
    issue = db.scalar(select(RecoveryIssue).where(RecoveryIssue.id == issue_id))

    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery issue not found.",
        )

    return issue


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
