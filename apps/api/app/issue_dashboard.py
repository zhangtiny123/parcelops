from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.common import utcnow
from app.models.recovery import RecoveryIssue


@dataclass(frozen=True)
class IssueMetricBucket:
    name: str
    count: int
    estimated_recoverable_amount: Decimal


@dataclass(frozen=True)
class IssueTrendPoint:
    date: date
    count: int
    estimated_recoverable_amount: Decimal


@dataclass(frozen=True)
class IssueDashboardSummary:
    total_issue_count: int
    total_recoverable_amount: Decimal
    issues_by_type: list[IssueMetricBucket]
    issues_by_provider: list[IssueMetricBucket]
    trend: list[IssueTrendPoint]


def get_issue_dashboard_summary(
    db: Session,
    *,
    trend_days: int = 30,
) -> IssueDashboardSummary:
    today = utcnow().date()
    start_day = today - timedelta(days=trend_days - 1)
    trend_cutoff = datetime.combine(start_day, time.min, tzinfo=timezone.utc)

    total_issue_count_expr = func.count(RecoveryIssue.id)
    total_recoverable_amount_expr = func.sum(RecoveryIssue.estimated_recoverable_amount)

    total_issue_count, total_recoverable_amount = db.execute(
        select(total_issue_count_expr, total_recoverable_amount_expr)
    ).one()

    return IssueDashboardSummary(
        total_issue_count=int(total_issue_count or 0),
        total_recoverable_amount=_money_or_zero(total_recoverable_amount),
        issues_by_type=_group_issue_metrics(db, RecoveryIssue.issue_type),
        issues_by_provider=_group_issue_metrics(db, RecoveryIssue.provider_name),
        trend=_load_issue_trend(
            db,
            start_day=start_day,
            end_day=today,
            trend_cutoff=trend_cutoff,
        ),
    )


def list_high_severity_issues(
    db: Session,
    *,
    limit: int = 5,
) -> list[RecoveryIssue]:
    amount_missing_rank = case(
        (RecoveryIssue.estimated_recoverable_amount.is_(None), 1),
        else_=0,
    )
    confidence_missing_rank = case(
        (RecoveryIssue.confidence.is_(None), 1),
        else_=0,
    )

    statement = (
        select(RecoveryIssue)
        .where(RecoveryIssue.severity == "high")
        .order_by(
            amount_missing_rank.asc(),
            RecoveryIssue.estimated_recoverable_amount.desc(),
            confidence_missing_rank.asc(),
            RecoveryIssue.confidence.desc(),
            RecoveryIssue.detected_at.desc(),
            RecoveryIssue.id.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(statement))


def _group_issue_metrics(
    db: Session,
    group_column: Any,
) -> list[IssueMetricBucket]:
    group_name_expr = group_column.label("name")
    count_expr = func.count(RecoveryIssue.id).label("count")
    total_recoverable_amount_expr = func.sum(
        RecoveryIssue.estimated_recoverable_amount
    ).label("estimated_recoverable_amount")

    statement = (
        select(group_name_expr, count_expr, total_recoverable_amount_expr)
        .group_by(group_column)
        .order_by(count_expr.desc(), group_name_expr.asc())
    )

    rows = db.execute(statement).all()
    return [
        IssueMetricBucket(
            name=row.name,
            count=int(row.count),
            estimated_recoverable_amount=_money_or_zero(
                row.estimated_recoverable_amount
            ),
        )
        for row in rows
    ]


def _load_issue_trend(
    db: Session,
    *,
    start_day: date,
    end_day: date,
    trend_cutoff: datetime,
) -> list[IssueTrendPoint]:
    bucket_day_expr = func.date(RecoveryIssue.detected_at).label("bucket_day")
    count_expr = func.count(RecoveryIssue.id).label("count")
    total_recoverable_amount_expr = func.sum(
        RecoveryIssue.estimated_recoverable_amount
    ).label("estimated_recoverable_amount")

    statement = (
        select(bucket_day_expr, count_expr, total_recoverable_amount_expr)
        .where(RecoveryIssue.detected_at >= trend_cutoff)
        .group_by(bucket_day_expr)
        .order_by(bucket_day_expr.asc())
    )

    rows_by_day = {
        _normalize_bucket_day(row.bucket_day): IssueTrendPoint(
            date=_normalize_bucket_day(row.bucket_day),
            count=int(row.count),
            estimated_recoverable_amount=_money_or_zero(
                row.estimated_recoverable_amount
            ),
        )
        for row in db.execute(statement).all()
    }

    trend: list[IssueTrendPoint] = []
    current_day = start_day
    while current_day <= end_day:
        trend.append(
            rows_by_day.get(
                current_day,
                IssueTrendPoint(
                    date=current_day,
                    count=0,
                    estimated_recoverable_amount=Decimal("0.00"),
                ),
            )
        )
        current_day += timedelta(days=1)

    return trend


def _normalize_bucket_day(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _money_or_zero(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))
