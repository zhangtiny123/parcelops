from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recovery import (
    RECOVERY_CASE_STATUS_OPEN,
    RecoveryCase,
    RecoveryIssue,
)
from app.recovery_cases import (
    RecoveryCaseValidationError,
    build_case_draft,
    load_linked_issues,
    normalize_case_status,
    normalize_case_title,
    normalize_optional_text,
    sum_recoverable_amount,
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
    draft_internal_note: Optional[str]
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
    draft_internal_note: Optional[str] = None


class RecoveryCaseRegenerateDraftRequest(BaseModel):
    title: Optional[str] = None


def _read_case_or_404(case_id: str, db: Session) -> RecoveryCase:
    recovery_case = db.get(RecoveryCase, case_id)
    if recovery_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery case not found.",
        )
    return recovery_case


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
        draft_internal_note=recovery_case.draft_internal_note,
        estimated_recoverable_amount=sum_recoverable_amount(issues),
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
    try:
        case_draft = build_case_draft(request.issue_ids, db, title=request.title)
    except RecoveryCaseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    recovery_case = RecoveryCase(
        title=case_draft.title,
        status=RECOVERY_CASE_STATUS_OPEN,
        issue_ids=case_draft.issue_ids,
        draft_summary=case_draft.draft_summary,
        draft_email=case_draft.draft_email,
        draft_internal_note=case_draft.draft_internal_note,
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

    return _build_case_detail_read(recovery_case, case_draft.issues)


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
        for issue in db.scalars(
            select(RecoveryIssue).where(RecoveryIssue.id.in_(all_issue_ids))
        )
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
    try:
        issues = load_linked_issues(list(recovery_case.issue_ids), db)
    except RecoveryCaseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _build_case_detail_read(recovery_case, issues)


@router.put("/{case_id}", response_model=RecoveryCaseDetailRead)
def update_recovery_case(
    case_id: str,
    request: RecoveryCaseUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailRead:
    recovery_case = _read_case_or_404(case_id, db)
    try:
        issues = load_linked_issues(list(recovery_case.issue_ids), db)
        normalized_title = normalize_case_title(request.title, issues)
        normalized_status = normalize_case_status(request.status)
    except RecoveryCaseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    recovery_case.title = normalized_title
    recovery_case.status = normalized_status
    recovery_case.draft_summary = normalize_optional_text(request.draft_summary)
    recovery_case.draft_email = normalize_optional_text(request.draft_email)
    recovery_case.draft_internal_note = normalize_optional_text(
        request.draft_internal_note
    )

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


@router.post("/{case_id}/drafts/regenerate", response_model=RecoveryCaseDetailRead)
def regenerate_recovery_case_drafts(
    case_id: str,
    request: RecoveryCaseRegenerateDraftRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailRead:
    recovery_case = _read_case_or_404(case_id, db)

    try:
        case_draft = build_case_draft(
            list(recovery_case.issue_ids),
            db,
            title=request.title or recovery_case.title,
        )
    except RecoveryCaseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    recovery_case.title = case_draft.title
    recovery_case.draft_summary = case_draft.draft_summary
    recovery_case.draft_email = case_draft.draft_email
    recovery_case.draft_internal_note = case_draft.draft_internal_note

    try:
        db.add(recovery_case)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate recovery case drafts.",
        ) from exc

    return _build_case_detail_read(recovery_case, case_draft.issues)
