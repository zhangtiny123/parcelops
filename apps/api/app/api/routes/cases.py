from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recovery import (
    RECOVERY_CASE_STATUSES,
    RECOVERY_CASE_STATUS_OPEN,
    RecoveryCase,
    RecoveryIssue,
)

router = APIRouter(prefix="/cases", tags=["cases"])


class RecoveryCaseLinkedIssueRead(BaseModel):
    id: str
    issue_type: str
    provider_name: str
    severity: str
    status: str
    estimated_recoverable_amount: Optional[Decimal]
    summary: str
    detected_at: datetime


class RecoveryCaseListRead(BaseModel):
    id: str
    title: str
    status: str
    issue_count: int
    issue_ids: list[str]
    draft_summary: Optional[str]
    draft_email: Optional[str]
    estimated_recoverable_amount: Decimal
    created_at: datetime
    updated_at: datetime


class RecoveryCaseDetailRead(RecoveryCaseListRead):
    issues: list[RecoveryCaseLinkedIssueRead]


class RecoveryCaseCreateRequest(BaseModel):
    issue_ids: list[str]
    title: Optional[str] = None


class RecoveryCaseUpdateRequest(BaseModel):
    title: str
    status: str
    draft_summary: Optional[str] = None
    draft_email: Optional[str] = None


def _format_currency(amount: Decimal) -> str:
    return f"${amount.quantize(Decimal('0.01')):,.2f}"


def _format_status_label(value: str) -> str:
    return " ".join(
        segment[:1].upper() + segment[1:]
        for segment in value.replace("-", "_").split("_")
        if segment
    )


def _money_or_zero(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _dedupe_issue_ids(issue_ids: list[str]) -> list[str]:
    normalized_issue_ids: list[str] = []
    seen_issue_ids: set[str] = set()

    for issue_id in issue_ids:
        normalized_issue_id = issue_id.strip()
        if not normalized_issue_id or normalized_issue_id in seen_issue_ids:
            continue
        normalized_issue_ids.append(normalized_issue_id)
        seen_issue_ids.add(normalized_issue_id)

    if not normalized_issue_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one recovery issue is required to create a case.",
        )

    return normalized_issue_ids


def _read_case_or_404(case_id: str, db: Session) -> RecoveryCase:
    recovery_case = db.get(RecoveryCase, case_id)
    if recovery_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery case not found.",
        )
    return recovery_case


def _load_linked_issues(issue_ids: list[str], db: Session) -> list[RecoveryIssue]:
    if not issue_ids:
        return []

    issues = list(
        db.scalars(select(RecoveryIssue).where(RecoveryIssue.id.in_(issue_ids)))
    )
    issues_by_id = {issue.id: issue for issue in issues}
    missing_issue_ids = [issue_id for issue_id in issue_ids if issue_id not in issues_by_id]
    if missing_issue_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Recovery issues not found: "
                + ", ".join(sorted(missing_issue_ids))
                + "."
            ),
        )

    return [issues_by_id[issue_id] for issue_id in issue_ids]


def _normalize_case_title(title: str | None, issues: list[RecoveryIssue]) -> str:
    normalized_title = (title or "").strip()
    if normalized_title:
        return normalized_title

    provider_names = sorted({issue.provider_name for issue in issues})
    primary_provider = provider_names[0] if len(provider_names) == 1 else "Multi-provider"

    if len(issues) == 1:
        return f"{primary_provider} {_format_status_label(issues[0].issue_type)} case"

    return f"{primary_provider} recovery case ({len(issues)} issues)"


def _normalize_case_status(status_value: str) -> str:
    normalized_status = status_value.strip().lower()
    if normalized_status not in RECOVERY_CASE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recovery case status must be open, pending, or resolved.",
        )
    return normalized_status


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _sum_recoverable_amount(issues: list[RecoveryIssue]) -> Decimal:
    total = Decimal("0.00")
    for issue in issues:
        total += _money_or_zero(issue.estimated_recoverable_amount)
    return total.quantize(Decimal("0.01"))


def _build_default_summary(issues: list[RecoveryIssue]) -> str:
    total_amount = _format_currency(_sum_recoverable_amount(issues))
    issue_lines = [
        (
            f"{index}. {_format_status_label(issue.issue_type)} with {issue.provider_name} "
            f"({issue.summary}; estimated {_format_currency(_money_or_zero(issue.estimated_recoverable_amount))})"
        )
        for index, issue in enumerate(issues, start=1)
    ]

    return (
        f"This recovery case groups {len(issues)} issue(s) with an estimated recoverable value of {total_amount}.\n\n"
        "Included issues:\n"
        + "\n".join(issue_lines)
    )


def _build_default_email(title: str, issues: list[RecoveryIssue]) -> str:
    total_amount = _format_currency(_sum_recoverable_amount(issues))
    issue_lines = [
        f"- {_format_status_label(issue.issue_type)}: {issue.summary}"
        for issue in issues
    ]

    return (
        "Subject: Recovery review request\n\n"
        "Hello,\n\n"
        f"We created the recovery case \"{title}\" for {len(issues)} issue(s) totaling {total_amount}.\n\n"
        "Included items:\n"
        + "\n".join(issue_lines)
        + "\n\nPlease review these charges and confirm the next recovery step.\n\nThank you."
    )


def _build_linked_issue_read(issue: RecoveryIssue) -> RecoveryCaseLinkedIssueRead:
    return RecoveryCaseLinkedIssueRead(
        id=issue.id,
        issue_type=issue.issue_type,
        provider_name=issue.provider_name,
        severity=issue.severity,
        status=issue.status,
        estimated_recoverable_amount=issue.estimated_recoverable_amount,
        summary=issue.summary,
        detected_at=issue.detected_at,
    )


def _build_case_list_read(
    recovery_case: RecoveryCase,
    issues: list[RecoveryIssue],
) -> RecoveryCaseListRead:
    return RecoveryCaseListRead(
        id=recovery_case.id,
        title=recovery_case.title,
        status=recovery_case.status,
        issue_count=len(issues),
        issue_ids=list(recovery_case.issue_ids),
        draft_summary=recovery_case.draft_summary,
        draft_email=recovery_case.draft_email,
        estimated_recoverable_amount=_sum_recoverable_amount(issues),
        created_at=recovery_case.created_at,
        updated_at=recovery_case.updated_at,
    )


def _build_case_detail_read(
    recovery_case: RecoveryCase,
    issues: list[RecoveryIssue],
) -> RecoveryCaseDetailRead:
    case_list_read = _build_case_list_read(recovery_case, issues)

    return RecoveryCaseDetailRead(
        **case_list_read.model_dump(),
        issues=[_build_linked_issue_read(issue) for issue in issues],
    )


@router.post(
    "",
    response_model=RecoveryCaseDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recovery_case(
    request: RecoveryCaseCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailRead:
    issue_ids = _dedupe_issue_ids(request.issue_ids)
    issues = _load_linked_issues(issue_ids, db)
    title = _normalize_case_title(request.title, issues)

    recovery_case = RecoveryCase(
        title=title,
        status=RECOVERY_CASE_STATUS_OPEN,
        issue_ids=issue_ids,
        draft_summary=_build_default_summary(issues),
        draft_email=_build_default_email(title, issues),
    )

    try:
        db.add(recovery_case)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create recovery case.",
        ) from exc

    return _build_case_detail_read(recovery_case, issues)


@router.get("", response_model=list[RecoveryCaseListRead])
def list_recovery_cases(
    db: Annotated[Session, Depends(get_db)],
) -> list[RecoveryCaseListRead]:
    recovery_cases = list(
        db.scalars(
            select(RecoveryCase).order_by(
                RecoveryCase.updated_at.desc(),
                RecoveryCase.id.desc(),
            )
        )
    )

    all_issue_ids = list(
        {
            issue_id
            for recovery_case in recovery_cases
            for issue_id in recovery_case.issue_ids
        }
    )
    issues_by_id = {
        issue.id: issue
        for issue in db.scalars(select(RecoveryIssue).where(RecoveryIssue.id.in_(all_issue_ids)))
    }

    case_reads: list[RecoveryCaseListRead] = []
    for recovery_case in recovery_cases:
        issues = [
            issues_by_id[issue_id]
            for issue_id in recovery_case.issue_ids
            if issue_id in issues_by_id
        ]
        case_reads.append(_build_case_list_read(recovery_case, issues))

    return case_reads


@router.get("/{case_id}", response_model=RecoveryCaseDetailRead)
def read_recovery_case(
    case_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailRead:
    recovery_case = _read_case_or_404(case_id, db)
    issues = _load_linked_issues(list(recovery_case.issue_ids), db)
    return _build_case_detail_read(recovery_case, issues)


@router.put("/{case_id}", response_model=RecoveryCaseDetailRead)
def update_recovery_case(
    case_id: str,
    request: RecoveryCaseUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailRead:
    recovery_case = _read_case_or_404(case_id, db)
    issues = _load_linked_issues(list(recovery_case.issue_ids), db)

    normalized_title = _normalize_case_title(request.title, issues)
    normalized_status = _normalize_case_status(request.status)

    recovery_case.title = normalized_title
    recovery_case.status = normalized_status
    recovery_case.draft_summary = _normalize_optional_text(request.draft_summary)
    recovery_case.draft_email = _normalize_optional_text(request.draft_email)

    try:
        db.add(recovery_case)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update recovery case.",
        ) from exc

    return _build_case_detail_read(recovery_case, issues)
