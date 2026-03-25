from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.recovery import RecoveryIssue


@dataclass(frozen=True)
class DisputeDraftArtifacts:
    case_summary: str
    dispute_email: str
    internal_next_step_note: str


@dataclass(frozen=True)
class IssueEvidenceSnapshot:
    issue_id: str
    issue_type_label: str
    provider_name: str
    estimated_recoverable_amount: Decimal
    estimated_recoverable_amount_display: str
    summary: str
    fact_lines: tuple[str, ...]


_EVIDENCE_KEY_PRIORITY = {
    "invoice_number": 0,
    "invoice_date": 1,
    "tracking_number": 2,
    "duplicate_count": 3,
    "service_level_billed": 4,
    "billed_weight_lb": 5,
    "modeled_weight_lb": 6,
    "zone_billed": 7,
}


def generate_dispute_draft_artifacts(
    *,
    title: str,
    issues: list[RecoveryIssue],
) -> DisputeDraftArtifacts:
    issue_snapshots = [_build_issue_snapshot(issue) for issue in issues]
    total_amount = _format_currency(
        sum(
            (snapshot.estimated_recoverable_amount for snapshot in issue_snapshots),
            start=Decimal("0.00"),
        )
    )
    provider_names = sorted({snapshot.provider_name for snapshot in issue_snapshots})
    provider_summary = _describe_provider_scope(provider_names)

    return DisputeDraftArtifacts(
        case_summary=_build_case_summary(
            title=title,
            provider_summary=provider_summary,
            total_amount=total_amount,
            issue_snapshots=issue_snapshots,
        ),
        dispute_email=_build_dispute_email(
            title=title,
            provider_names=provider_names,
            total_amount=total_amount,
            issue_snapshots=issue_snapshots,
        ),
        internal_next_step_note=_build_internal_next_step_note(
            title=title,
            provider_names=provider_names,
            total_amount=total_amount,
            issue_snapshots=issue_snapshots,
        ),
    )


def _build_case_summary(
    *,
    title: str,
    provider_summary: str,
    total_amount: str,
    issue_snapshots: list[IssueEvidenceSnapshot],
) -> str:
    issue_lines = [
        (
            f"{index}. {snapshot.issue_id} | {snapshot.issue_type_label} | "
            f"{snapshot.provider_name} | {snapshot.estimated_recoverable_amount_display}. "
            f"{snapshot.summary} Evidence: {_format_fact_sentence(snapshot.fact_lines)}."
        )
        for index, snapshot in enumerate(issue_snapshots, start=1)
    ]

    lines = [
        (
            f'Case "{title}" groups {len(issue_snapshots)} recovery issue(s) for '
            f"{provider_summary} totaling {total_amount} in estimated recoveries."
        ),
        "",
        "Evidence snapshot:",
        *issue_lines,
    ]

    if len({snapshot.provider_name for snapshot in issue_snapshots}) > 1:
        lines.extend(
            [
                "",
                "Operator note: split outbound disputes by provider before sending.",
            ]
        )

    return "\n".join(lines)


def _build_dispute_email(
    *,
    title: str,
    provider_names: list[str],
    total_amount: str,
    issue_snapshots: list[IssueEvidenceSnapshot],
) -> str:
    if len(provider_names) == 1:
        subject = f"Subject: Dispute review request for {provider_names[0]} charges"
        greeting = f"Hello {provider_names[0]} billing team,"
        multi_provider_note = None
    else:
        subject = "Subject: Recovery review request for multi-provider billing charges"
        greeting = "Hello,"
        multi_provider_note = "This draft spans multiple providers. Split the line items into provider-specific outreach before sending."

    issue_sections = []
    for index, snapshot in enumerate(issue_snapshots, start=1):
        detail_lines = [
            f"{index}. {snapshot.issue_type_label} ({snapshot.issue_id})",
            f"Provider: {snapshot.provider_name}",
            f"Estimated recoverable amount: {snapshot.estimated_recoverable_amount_display}",
            f"Basis: {snapshot.summary}",
        ]
        detail_lines.extend(snapshot.fact_lines)
        issue_sections.append("\n".join(detail_lines))

    lines = [
        subject,
        "",
        greeting,
        "",
        (
            f'We are requesting review of the billing items grouped in case "{title}". '
            f"The estimated recoverable amount represented below is {total_amount}."
        ),
    ]
    if multi_provider_note:
        lines.extend(["", multi_provider_note])

    lines.extend(
        [
            "",
            "Please review the following evidence-backed line items:",
            "",
            "\n\n".join(issue_sections),
            "",
            "Please confirm the credit, adjustment, or supporting explanation for each item.",
            "",
            "Thank you,",
            "ParcelOps Recovery Team",
        ]
    )
    return "\n".join(lines)


def _build_internal_next_step_note(
    *,
    title: str,
    provider_names: list[str],
    total_amount: str,
    issue_snapshots: list[IssueEvidenceSnapshot],
) -> str:
    lines = [
        f'Internal next-step note for "{title}"',
        f"- Confirm the evidence packet for {len(issue_snapshots)} issue(s) totaling {total_amount}.",
    ]

    for snapshot in issue_snapshots:
        lines.append(
            (
                f"- Review {snapshot.issue_id} ({snapshot.issue_type_label}, "
                f"{snapshot.estimated_recoverable_amount_display}) against "
                f"{_format_fact_sentence(snapshot.fact_lines, limit=3)}."
            )
        )

    if len(provider_names) == 1:
        lines.append(
            f"- Send the dispute draft to {provider_names[0]} and move the case to pending after submission."
        )
    else:
        lines.append(
            "- Split this case into provider-specific outreach before sending any external dispute."
        )

    lines.append(
        "- Track credits, carrier responses, and follow-up dates in the case record until resolution."
    )

    return "\n".join(lines)


def _build_issue_snapshot(issue: RecoveryIssue) -> IssueEvidenceSnapshot:
    estimated_recoverable_amount = _money_or_zero(issue.estimated_recoverable_amount)

    return IssueEvidenceSnapshot(
        issue_id=issue.id,
        issue_type_label=_format_status_label(issue.issue_type),
        provider_name=issue.provider_name,
        estimated_recoverable_amount=estimated_recoverable_amount,
        estimated_recoverable_amount_display=_format_currency(
            estimated_recoverable_amount
        ),
        summary=issue.summary,
        fact_lines=tuple(_collect_fact_lines(issue)),
    )


def _collect_fact_lines(issue: RecoveryIssue) -> list[str]:
    fact_lines: list[str] = []
    seen_facts: set[tuple[str, str]] = set()

    def add_fact(label: str, value: Any) -> None:
        normalized_value = _normalize_fact_value(value)
        if normalized_value is None:
            return
        fact_key = (label, normalized_value)
        if fact_key in seen_facts:
            return
        seen_facts.add(fact_key)
        fact_lines.append(f"{label}: {normalized_value}")

    for key, value in sorted(
        issue.evidence_json.items(),
        key=lambda item: (_EVIDENCE_KEY_PRIORITY.get(item[0], 99), item[0]),
    ):
        add_fact(_format_fact_label(key), value)

    add_fact("Shipment ID", issue.shipment_id)
    add_fact("Parcel invoice line ID", issue.parcel_invoice_line_id)
    add_fact("3PL invoice line ID", issue.three_pl_invoice_line_id)
    add_fact("Detected date", issue.detected_at.date().isoformat())
    add_fact("Issue status", issue.status)
    add_fact("Issue severity", issue.severity)

    return fact_lines


def _format_fact_label(key: str) -> str:
    words = key.replace("-", "_").split("_")
    label = " ".join(word[:1].upper() + word[1:] for word in words if word)
    if label.endswith(" Id"):
        return label[:-3] + " ID"
    return label


def _format_fact_sentence(
    fact_lines: tuple[str, ...],
    *,
    limit: int | None = None,
) -> str:
    selected_fact_lines = list(fact_lines[:limit] if limit is not None else fact_lines)
    if not selected_fact_lines:
        return "no additional evidence fields captured"
    return "; ".join(selected_fact_lines)


def _describe_provider_scope(provider_names: list[str]) -> str:
    if not provider_names:
        return "unknown providers"
    if len(provider_names) == 1:
        return provider_names[0]
    return f"{len(provider_names)} providers ({', '.join(provider_names)})"


def _normalize_fact_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, (int, float, str)):
        normalized_value = str(value).strip()
        return normalized_value or None
    if isinstance(value, list):
        normalized_items = [
            normalized_item
            for item in value
            if (normalized_item := _normalize_fact_value(item)) is not None
        ]
        if normalized_items:
            return ", ".join(normalized_items)
        return None
    return None


def _money_or_zero(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _format_currency(amount: Decimal) -> str:
    return f"${amount.quantize(Decimal('0.01')):,.2f}"


def _format_status_label(value: str) -> str:
    return " ".join(
        segment[:1].upper() + segment[1:]
        for segment in value.replace("-", "_").split("_")
        if segment
    )
