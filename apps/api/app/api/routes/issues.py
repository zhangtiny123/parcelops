from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import logging
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.issue_dashboard import get_issue_dashboard_summary, list_high_severity_issues
from app.observability import (
    complete_issue_detection_run,
    fail_issue_detection_run,
    start_issue_detection_run,
)
from app.models.observability import IssueDetectionRun
from app.models.recovery import RecoveryIssue
from app.recovery_issue_detection import run_issue_detection
from app.structured_logging import get_logger, log_event

router = APIRouter(prefix="/issues", tags=["issues"])
logger = get_logger(__name__)


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
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
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
    run = start_issue_detection_run(db)
    db.commit()
    db.refresh(run)
    log_event(
        logger,
        logging.INFO,
        "issue_detection.started",
        run_id=run.id,
        status=run.status,
    )

    try:
        detection_result = run_issue_detection(db)
        run = db.get(IssueDetectionRun, run.id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reload issue detection run.",
            )
        complete_issue_detection_run(db, run=run, result=detection_result)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        persisted_run = db.get(IssueDetectionRun, run.id)
        if persisted_run is not None:
            fail_issue_detection_run(
                db,
                run=persisted_run,
                error_message=str(exc) or "Failed to run issue detection.",
            )
            db.commit()
        logger.exception(
            "issue_detection.failed",
            extra={
                "event": "issue_detection.failed",
                "run_id": run.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run issue detection.",
        ) from exc

    log_event(
        logger,
        logging.INFO,
        "issue_detection.completed",
        run_id=run.id,
        status=run.status,
        created_count=run.created_count,
        updated_count=run.updated_count,
        unchanged_count=run.unchanged_count,
        deleted_duplicate_count=run.deleted_duplicate_count,
        total_issue_count=run.total_issue_count,
    )
    return RecoveryIssueDetectionRead(
        run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
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
