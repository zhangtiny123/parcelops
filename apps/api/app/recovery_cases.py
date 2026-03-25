from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dispute_draft_generator import generate_dispute_draft_artifacts
from app.models.recovery import RECOVERY_CASE_STATUSES, RecoveryIssue


class RecoveryCaseValidationError(ValueError):
    """Raised when a recovery case request cannot be satisfied safely."""


@dataclass(frozen=True)
class RecoveryCaseDraft:
    issue_ids: list[str]
    title: str
    draft_summary: str
    draft_email: str
    draft_internal_note: str
    estimated_recoverable_amount: Decimal
    issues: list[RecoveryIssue]


def format_currency(amount: Decimal) -> str:
    return f"${amount.quantize(Decimal('0.01')):,.2f}"


def format_status_label(value: str) -> str:
    return " ".join(
        segment[:1].upper() + segment[1:]
        for segment in value.replace("-", "_").split("_")
        if segment
    )


def money_or_zero(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def dedupe_issue_ids(issue_ids: list[str]) -> list[str]:
    normalized_issue_ids: list[str] = []
    seen_issue_ids: set[str] = set()

    for issue_id in issue_ids:
        normalized_issue_id = issue_id.strip()
        if not normalized_issue_id or normalized_issue_id in seen_issue_ids:
            continue
        normalized_issue_ids.append(normalized_issue_id)
        seen_issue_ids.add(normalized_issue_id)

    if not normalized_issue_ids:
        raise RecoveryCaseValidationError(
            "At least one recovery issue is required to create a case."
        )

    return normalized_issue_ids


def load_linked_issues(issue_ids: list[str], db: Session) -> list[RecoveryIssue]:
    if not issue_ids:
        return []

    issues = list(
        db.scalars(select(RecoveryIssue).where(RecoveryIssue.id.in_(issue_ids)))
    )
    issues_by_id = {issue.id: issue for issue in issues}
    missing_issue_ids = [
        issue_id for issue_id in issue_ids if issue_id not in issues_by_id
    ]
    if missing_issue_ids:
        raise RecoveryCaseValidationError(
            "Recovery issues not found: " + ", ".join(sorted(missing_issue_ids)) + "."
        )

    return [issues_by_id[issue_id] for issue_id in issue_ids]


def normalize_case_title(title: Optional[str], issues: list[RecoveryIssue]) -> str:
    normalized_title = (title or "").strip()
    if normalized_title:
        return normalized_title

    provider_names = sorted({issue.provider_name for issue in issues})
    primary_provider = (
        provider_names[0] if len(provider_names) == 1 else "Multi-provider"
    )

    if len(issues) == 1:
        return f"{primary_provider} {format_status_label(issues[0].issue_type)} case"

    return f"{primary_provider} recovery case ({len(issues)} issues)"


def normalize_case_status(status_value: str) -> str:
    normalized_status = status_value.strip().lower()
    if normalized_status not in RECOVERY_CASE_STATUSES:
        raise RecoveryCaseValidationError(
            "Recovery case status must be open, pending, or resolved."
        )
    return normalized_status


def normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def sum_recoverable_amount(issues: list[RecoveryIssue]) -> Decimal:
    total = Decimal("0.00")
    for issue in issues:
        total += money_or_zero(issue.estimated_recoverable_amount)
    return total.quantize(Decimal("0.01"))


def build_default_summary(issues: list[RecoveryIssue]) -> str:
    total_amount = format_currency(sum_recoverable_amount(issues))
    issue_lines = [
        (
            f"{index}. {format_status_label(issue.issue_type)} with {issue.provider_name} "
            f"({issue.summary}; estimated {format_currency(money_or_zero(issue.estimated_recoverable_amount))})"
        )
        for index, issue in enumerate(issues, start=1)
    ]

    return (
        f"This recovery case groups {len(issues)} issue(s) with an estimated recoverable value of {total_amount}.\n\n"
        "Included issues:\n" + "\n".join(issue_lines)
    )


def build_default_email(title: str, issues: list[RecoveryIssue]) -> str:
    total_amount = format_currency(sum_recoverable_amount(issues))
    issue_lines = [
        f"- {format_status_label(issue.issue_type)}: {issue.summary}"
        for issue in issues
    ]

    return (
        "Subject: Recovery review request\n\n"
        "Hello,\n\n"
        f'We created the recovery case "{title}" for {len(issues)} issue(s) totaling {total_amount}.\n\n'
        "Included items:\n"
        + "\n".join(issue_lines)
        + "\n\nPlease review these charges and confirm the next recovery step.\n\nThank you."
    )


def build_case_draft(
    issue_ids: list[str],
    db: Session,
    *,
    title: Optional[str] = None,
) -> RecoveryCaseDraft:
    normalized_issue_ids = dedupe_issue_ids(issue_ids)
    issues = load_linked_issues(normalized_issue_ids, db)
    normalized_title = normalize_case_title(title, issues)
    estimated_recoverable_amount = sum_recoverable_amount(issues)
    dispute_draft_artifacts = generate_dispute_draft_artifacts(
        title=normalized_title,
        issues=issues,
    )

    return RecoveryCaseDraft(
        issue_ids=normalized_issue_ids,
        title=normalized_title,
        draft_summary=dispute_draft_artifacts.case_summary,
        draft_email=dispute_draft_artifacts.dispute_email,
        draft_internal_note=dispute_draft_artifacts.internal_next_step_note,
        estimated_recoverable_amount=estimated_recoverable_amount,
        issues=issues,
    )
