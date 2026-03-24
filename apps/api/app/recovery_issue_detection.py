from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing import ParcelInvoiceLine, RateCardRule, ThreePLInvoiceLine
from app.models.common import utcnow
from app.models.fulfillment import Shipment
from app.models.recovery import RecoveryIssue

ISSUE_STATUS_OPEN = "open"
PARCEL_PROVIDER_TYPE = "parcel"
THREE_PL_PROVIDER_TYPE = "3pl"
THREE_PL_FALLBACK_PROVIDER_NAME = "3PL"
MANAGED_ISSUE_TYPES = (
    "duplicate_charge",
    "billed_weight_mismatch",
    "zone_mismatch",
    "service_level_mismatch",
    "missing_contracted_rate_or_discount",
    "unexpected_surcharge_spike",
    "invoice_line_without_matched_shipment",
    "unexpected_pick_or_pack_charge",
    "incorrect_unit_rate_vs_rate_card",
    "invoice_line_without_matched_order_or_shipment",
)
SERVICE_LEVEL_RANKS = {
    "ground": 1,
    "2day": 2,
    "overnight": 3,
}


@dataclass(frozen=True)
class IssueCandidate:
    issue_type: str
    provider_name: str
    severity: str
    status: str
    confidence: Decimal | None
    estimated_recoverable_amount: Decimal | None
    shipment_id: str | None
    parcel_invoice_line_id: str | None
    three_pl_invoice_line_id: str | None
    summary: str
    evidence_json: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_key(self) -> tuple[str, str, str, str]:
        return (
            self.issue_type,
            self.shipment_id or "",
            self.parcel_invoice_line_id or "",
            self.three_pl_invoice_line_id or "",
        )


@dataclass(frozen=True)
class DetectionResult:
    created_count: int
    updated_count: int
    unchanged_count: int
    deleted_duplicate_count: int
    total_issue_count: int
    counts_by_issue_type: dict[str, int]


def run_issue_detection(db: Session) -> DetectionResult:
    parcel_lines = list(db.scalars(select(ParcelInvoiceLine)))
    three_pl_lines = list(db.scalars(select(ThreePLInvoiceLine)))
    shipments = {shipment.id: shipment for shipment in db.scalars(select(Shipment))}
    rate_card_rules = list(db.scalars(select(RateCardRule)))

    raw_candidates = list(
        _collect_issue_candidates(
            parcel_lines=parcel_lines,
            three_pl_lines=three_pl_lines,
            shipments=shipments,
            rate_card_rules=rate_card_rules,
        )
    )
    candidates = list(
        {candidate.identity_key: candidate for candidate in raw_candidates}.values()
    )
    counts_by_issue_type = dict(
        sorted(Counter(candidate.issue_type for candidate in candidates).items())
    )

    existing_issues = list(
        db.scalars(
            select(RecoveryIssue).where(
                RecoveryIssue.issue_type.in_(MANAGED_ISSUE_TYPES)
            )
        )
    )
    existing_by_key: dict[tuple[str, str, str, str], RecoveryIssue] = {}
    deleted_duplicate_count = 0

    for issue in sorted(existing_issues, key=_existing_issue_sort_key):
        identity_key = _issue_identity_key(issue)
        canonical_issue = existing_by_key.get(identity_key)
        if canonical_issue is None:
            existing_by_key[identity_key] = issue
            continue
        db.delete(issue)
        deleted_duplicate_count += 1

    created_count = 0
    updated_count = 0
    unchanged_count = 0

    for candidate in candidates:
        existing_issue = existing_by_key.get(candidate.identity_key)
        if existing_issue is None:
            db.add(
                RecoveryIssue(
                    issue_type=candidate.issue_type,
                    provider_name=candidate.provider_name,
                    severity=candidate.severity,
                    status=candidate.status,
                    confidence=candidate.confidence,
                    estimated_recoverable_amount=candidate.estimated_recoverable_amount,
                    shipment_id=candidate.shipment_id,
                    parcel_invoice_line_id=candidate.parcel_invoice_line_id,
                    three_pl_invoice_line_id=candidate.three_pl_invoice_line_id,
                    summary=candidate.summary,
                    evidence_json=candidate.evidence_json,
                    detected_at=utcnow(),
                )
            )
            created_count += 1
            continue

        if _issue_matches_candidate(existing_issue, candidate):
            unchanged_count += 1
            continue

        existing_issue.provider_name = candidate.provider_name
        existing_issue.severity = candidate.severity
        existing_issue.status = candidate.status
        existing_issue.confidence = candidate.confidence
        existing_issue.estimated_recoverable_amount = (
            candidate.estimated_recoverable_amount
        )
        existing_issue.summary = candidate.summary
        existing_issue.evidence_json = candidate.evidence_json
        existing_issue.detected_at = utcnow()
        updated_count += 1

    return DetectionResult(
        created_count=created_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        deleted_duplicate_count=deleted_duplicate_count,
        total_issue_count=len(candidates),
        counts_by_issue_type=counts_by_issue_type,
    )


def _collect_issue_candidates(
    *,
    parcel_lines: list[ParcelInvoiceLine],
    three_pl_lines: list[ThreePLInvoiceLine],
    shipments: dict[str, Shipment],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    yield from _detect_duplicate_charges(parcel_lines, shipments)
    yield from _detect_billed_weight_mismatches(
        parcel_lines, shipments, rate_card_rules
    )
    yield from _detect_zone_mismatches(parcel_lines, shipments, rate_card_rules)
    yield from _detect_service_level_mismatches(
        parcel_lines,
        shipments,
        rate_card_rules,
    )
    yield from _detect_missing_contracted_rates(parcel_lines, rate_card_rules)
    yield from _detect_unexpected_surcharge_spikes(parcel_lines, rate_card_rules)
    yield from _detect_orphan_parcel_invoice_lines(parcel_lines)
    yield from _detect_unexpected_pick_or_pack_charges(three_pl_lines, rate_card_rules)
    yield from _detect_incorrect_three_pl_rates(three_pl_lines, rate_card_rules)
    yield from _detect_orphan_three_pl_invoice_lines(
        three_pl_lines,
        shipments,
        rate_card_rules,
    )


def _detect_duplicate_charges(
    parcel_lines: list[ParcelInvoiceLine],
    shipments: dict[str, Shipment],
) -> Iterable[IssueCandidate]:
    grouped_lines: dict[tuple[str, ...], list[ParcelInvoiceLine]] = defaultdict(list)

    for line in parcel_lines:
        grouped_lines[
            (
                line.invoice_number,
                line.tracking_number,
                line.carrier,
                line.charge_type,
                line.service_level_billed or "",
                _decimal_text(line.billed_weight_lb) or "",
                line.zone_billed or "",
                _decimal_text(line.amount) or "",
                line.currency,
            )
        ].append(line)

    for grouped in grouped_lines.values():
        if len(grouped) < 2:
            continue

        sorted_group = sorted(grouped, key=_parcel_line_sort_key)
        canonical_line = sorted_group[0]
        shipment = shipments.get(canonical_line.shipment_id or "")
        duplicate_total = len(sorted_group) - 1

        for duplicate_line in sorted_group[1:]:
            yield IssueCandidate(
                issue_type="duplicate_charge",
                provider_name=duplicate_line.carrier,
                severity="high",
                status=ISSUE_STATUS_OPEN,
                confidence=Decimal("0.9950"),
                estimated_recoverable_amount=duplicate_line.amount,
                shipment_id=duplicate_line.shipment_id,
                parcel_invoice_line_id=duplicate_line.id,
                three_pl_invoice_line_id=None,
                summary=(
                    f"Duplicate {duplicate_line.charge_type} charge on invoice "
                    f"{duplicate_line.invoice_number} for tracking "
                    f"{duplicate_line.tracking_number}."
                ),
                evidence_json={
                    "invoice_number": duplicate_line.invoice_number,
                    "tracking_number": duplicate_line.tracking_number,
                    "charge_type": duplicate_line.charge_type,
                    "canonical_parcel_invoice_line_id": canonical_line.id,
                    "duplicate_parcel_invoice_line_id": duplicate_line.id,
                    "duplicate_count": duplicate_total,
                    "service_level_billed": duplicate_line.service_level_billed,
                    "billed_weight_lb": _decimal_text(duplicate_line.billed_weight_lb),
                    "zone_billed": duplicate_line.zone_billed,
                    "amount": _decimal_text(duplicate_line.amount),
                    "raw_row_ref": duplicate_line.raw_row_ref,
                    "shipment_tracking_number": shipment.tracking_number
                    if shipment
                    else None,
                },
            )


def _detect_billed_weight_mismatches(
    parcel_lines: list[ParcelInvoiceLine],
    shipments: dict[str, Shipment],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if line.charge_type != "transportation" or line.billed_weight_lb is None:
            continue
        shipment = shipments.get(line.shipment_id or "")
        if shipment is None:
            continue

        expected_billable_weight = _expected_billable_weight(shipment)
        if (
            expected_billable_weight is None
            or line.billed_weight_lb <= expected_billable_weight
        ):
            continue

        expected_rate = _expected_parcel_rate(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=line.service_level_billed,
            zone=line.zone_billed,
            billed_weight_lb=expected_billable_weight,
        )
        recoverable_amount = _positive_difference(line.amount, expected_rate)
        if recoverable_amount is None:
            recoverable_amount = line.amount

        yield IssueCandidate(
            issue_type="billed_weight_mismatch",
            provider_name=line.carrier,
            severity="high",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9800"),
            estimated_recoverable_amount=recoverable_amount,
            shipment_id=line.shipment_id,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"Billed weight {line.billed_weight_lb} lb exceeds expected billable "
                f"weight {expected_billable_weight} lb for tracking "
                f"{line.tracking_number}."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "carrier": line.carrier,
                "invoice_number": line.invoice_number,
                "billed_weight_lb": _decimal_text(line.billed_weight_lb),
                "expected_billable_weight_lb": _decimal_text(expected_billable_weight),
                "shipment_weight_lb": _decimal_text(shipment.weight_lb),
                "shipment_dim_weight_lb": _decimal_text(shipment.dim_weight_lb),
                "service_level_billed": line.service_level_billed,
                "zone_billed": line.zone_billed,
                "amount": _decimal_text(line.amount),
                "expected_amount": _decimal_text(expected_rate),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_zone_mismatches(
    parcel_lines: list[ParcelInvoiceLine],
    shipments: dict[str, Shipment],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if line.charge_type != "transportation" or line.zone_billed is None:
            continue
        shipment = shipments.get(line.shipment_id or "")
        if (
            shipment is None
            or shipment.zone is None
            or line.zone_billed == shipment.zone
        ):
            continue

        expected_rate = _expected_parcel_rate(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=line.service_level_billed,
            zone=shipment.zone,
            billed_weight_lb=line.billed_weight_lb,
        )
        recoverable_amount = _positive_difference(line.amount, expected_rate)
        if recoverable_amount is None:
            billed_zone_value = _parse_int(line.zone_billed)
            actual_zone_value = _parse_int(shipment.zone)
            if (
                billed_zone_value is None
                or actual_zone_value is None
                or billed_zone_value <= actual_zone_value
            ):
                continue
            recoverable_amount = line.amount

        yield IssueCandidate(
            issue_type="zone_mismatch",
            provider_name=line.carrier,
            severity="high",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9750"),
            estimated_recoverable_amount=recoverable_amount,
            shipment_id=line.shipment_id,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"Zone {line.zone_billed} was billed for tracking "
                f"{line.tracking_number}, but shipment data shows zone {shipment.zone}."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "invoice_number": line.invoice_number,
                "zone_billed": line.zone_billed,
                "shipment_zone": shipment.zone,
                "service_level_billed": line.service_level_billed,
                "billed_weight_lb": _decimal_text(line.billed_weight_lb),
                "amount": _decimal_text(line.amount),
                "expected_amount": _decimal_text(expected_rate),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_service_level_mismatches(
    parcel_lines: list[ParcelInvoiceLine],
    shipments: dict[str, Shipment],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if line.charge_type != "transportation" or line.service_level_billed is None:
            continue
        shipment = shipments.get(line.shipment_id or "")
        if shipment is None or shipment.service_level is None:
            continue
        if _normalized_text(line.service_level_billed) == _normalized_text(
            shipment.service_level
        ):
            continue

        expected_rate = _expected_parcel_rate(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=shipment.service_level,
            zone=line.zone_billed,
            billed_weight_lb=line.billed_weight_lb,
        )
        recoverable_amount = _positive_difference(line.amount, expected_rate)
        billed_rank = _service_level_rank(line.service_level_billed)
        shipped_rank = _service_level_rank(shipment.service_level)
        if recoverable_amount is None and (
            billed_rank is None or shipped_rank is None or billed_rank <= shipped_rank
        ):
            continue

        yield IssueCandidate(
            issue_type="service_level_mismatch",
            provider_name=line.carrier,
            severity="medium",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9300"),
            estimated_recoverable_amount=recoverable_amount or line.amount,
            shipment_id=line.shipment_id,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"Parcel invoice billed {line.service_level_billed} for tracking "
                f"{line.tracking_number}, but shipment data shows {shipment.service_level}."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "invoice_number": line.invoice_number,
                "service_level_billed": line.service_level_billed,
                "shipment_service_level": shipment.service_level,
                "zone_billed": line.zone_billed,
                "billed_weight_lb": _decimal_text(line.billed_weight_lb),
                "amount": _decimal_text(line.amount),
                "expected_amount": _decimal_text(expected_rate),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_missing_contracted_rates(
    parcel_lines: list[ParcelInvoiceLine],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if not _can_attempt_parcel_rate_lookup(line):
            continue
        expected_rate = _expected_parcel_rate(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=line.service_level_billed,
            zone=line.zone_billed,
            billed_weight_lb=line.billed_weight_lb,
        )
        if expected_rate is not None:
            continue
        if _has_parcel_contract_reference(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=line.service_level_billed,
        ):
            continue

        yield IssueCandidate(
            issue_type="missing_contracted_rate_or_discount",
            provider_name=line.carrier,
            severity="medium",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.8200"),
            estimated_recoverable_amount=line.amount,
            shipment_id=line.shipment_id,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"No matching parcel rate card rule was found for "
                f"{line.charge_type} on invoice {line.invoice_number}."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "invoice_number": line.invoice_number,
                "carrier": line.carrier,
                "charge_type": line.charge_type,
                "service_level_billed": line.service_level_billed,
                "zone_billed": line.zone_billed,
                "billed_weight_lb": _decimal_text(line.billed_weight_lb),
                "amount": _decimal_text(line.amount),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_unexpected_surcharge_spikes(
    parcel_lines: list[ParcelInvoiceLine],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if line.charge_type == "transportation":
            continue
        expected_rate = _expected_parcel_rate(
            rate_card_rules,
            provider_name=line.carrier,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=line.service_level_billed,
            zone=line.zone_billed,
            billed_weight_lb=line.billed_weight_lb,
        )
        if expected_rate is None:
            continue

        recoverable_amount = _positive_difference(line.amount, expected_rate)
        if recoverable_amount is None or recoverable_amount <= Decimal("0.50"):
            continue

        yield IssueCandidate(
            issue_type="unexpected_surcharge_spike",
            provider_name=line.carrier,
            severity="medium",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9000"),
            estimated_recoverable_amount=recoverable_amount,
            shipment_id=line.shipment_id,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"{line.charge_type} on invoice {line.invoice_number} exceeds the "
                f"contracted surcharge rate."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "invoice_number": line.invoice_number,
                "charge_type": line.charge_type,
                "amount": _decimal_text(line.amount),
                "expected_amount": _decimal_text(expected_rate),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_orphan_parcel_invoice_lines(
    parcel_lines: list[ParcelInvoiceLine],
) -> Iterable[IssueCandidate]:
    for line in parcel_lines:
        if line.shipment_id is not None:
            continue
        yield IssueCandidate(
            issue_type="invoice_line_without_matched_shipment",
            provider_name=line.carrier,
            severity="high",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9950"),
            estimated_recoverable_amount=line.amount,
            shipment_id=None,
            parcel_invoice_line_id=line.id,
            three_pl_invoice_line_id=None,
            summary=(
                f"Parcel invoice line for tracking {line.tracking_number} could not "
                f"be matched to a canonical shipment."
            ),
            evidence_json={
                "tracking_number": line.tracking_number,
                "invoice_number": line.invoice_number,
                "carrier": line.carrier,
                "charge_type": line.charge_type,
                "amount": _decimal_text(line.amount),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _detect_unexpected_pick_or_pack_charges(
    three_pl_lines: list[ThreePLInvoiceLine],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    provider_name = _resolve_three_pl_provider_name(rate_card_rules)
    flagged_by_line_id: dict[str, IssueCandidate] = {}

    for line in three_pl_lines:
        if line.charge_type not in {"pick_fee", "packaging_fee"}:
            continue
        if line.quantity is None or line.quantity <= 1:
            continue

        recoverable_amount = None
        if line.unit_rate is not None:
            recoverable_amount = _quantize_money(
                line.unit_rate * Decimal(line.quantity - 1)
            )
        if recoverable_amount is None or recoverable_amount <= Decimal("0.00"):
            recoverable_amount = line.amount

        flagged_by_line_id[line.id] = IssueCandidate(
            issue_type="unexpected_pick_or_pack_charge",
            provider_name=provider_name,
            severity="medium",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9000"),
            estimated_recoverable_amount=recoverable_amount,
            shipment_id=None,
            parcel_invoice_line_id=None,
            three_pl_invoice_line_id=line.id,
            summary=(
                f"3PL {line.charge_type} line on invoice {line.invoice_number} billed "
                f"quantity {line.quantity}, which exceeds the expected single charge."
            ),
            evidence_json={
                "invoice_number": line.invoice_number,
                "charge_type": line.charge_type,
                "quantity": line.quantity,
                "unit_rate": _decimal_text(line.unit_rate),
                "amount": _decimal_text(line.amount),
                "raw_row_ref": line.raw_row_ref,
            },
        )

    grouped_lines: dict[tuple[str, str, str, str], list[ThreePLInvoiceLine]] = (
        defaultdict(list)
    )
    for line in three_pl_lines:
        if line.charge_type not in {"pick_fee", "packaging_fee"}:
            continue
        grouped_lines[
            (
                line.invoice_number,
                line.order_id or "",
                line.charge_type,
                line.sku or "",
            )
        ].append(line)

    for grouped in grouped_lines.values():
        if len(grouped) < 2:
            continue
        sorted_group = sorted(grouped, key=_three_pl_line_sort_key)
        for duplicate_line in sorted_group[1:]:
            flagged_by_line_id.setdefault(
                duplicate_line.id,
                IssueCandidate(
                    issue_type="unexpected_pick_or_pack_charge",
                    provider_name=provider_name,
                    severity="medium",
                    status=ISSUE_STATUS_OPEN,
                    confidence=Decimal("0.9000"),
                    estimated_recoverable_amount=duplicate_line.amount,
                    shipment_id=None,
                    parcel_invoice_line_id=None,
                    three_pl_invoice_line_id=duplicate_line.id,
                    summary=(
                        f"Duplicate 3PL {duplicate_line.charge_type} line found on "
                        f"invoice {duplicate_line.invoice_number}."
                    ),
                    evidence_json={
                        "invoice_number": duplicate_line.invoice_number,
                        "charge_type": duplicate_line.charge_type,
                        "order_id": duplicate_line.order_id,
                        "sku": duplicate_line.sku,
                        "amount": _decimal_text(duplicate_line.amount),
                        "raw_row_ref": duplicate_line.raw_row_ref,
                    },
                ),
            )

    yield from flagged_by_line_id.values()


def _detect_incorrect_three_pl_rates(
    three_pl_lines: list[ThreePLInvoiceLine],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    default_provider_name = _resolve_three_pl_provider_name(rate_card_rules)

    for line in three_pl_lines:
        actual_unit_rate = _actual_three_pl_unit_rate(line)
        if actual_unit_rate is None:
            continue

        matched_rule = _find_rate_card_rule(
            rate_card_rules,
            provider_type=THREE_PL_PROVIDER_TYPE,
            provider_name=None,
            charge_type=line.charge_type,
            invoice_date=line.invoice_date,
            service_level=None,
            zone=None,
            weight_lb=None,
        )
        if matched_rule is None:
            continue

        recoverable_per_unit = _positive_difference(
            actual_unit_rate,
            matched_rule.expected_rate,
        )
        if recoverable_per_unit is None:
            continue

        quantity = line.quantity or 1
        recoverable_amount = _quantize_money(recoverable_per_unit * Decimal(quantity))

        yield IssueCandidate(
            issue_type="incorrect_unit_rate_vs_rate_card",
            provider_name=matched_rule.provider_name or default_provider_name,
            severity="high",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9800"),
            estimated_recoverable_amount=recoverable_amount,
            shipment_id=None,
            parcel_invoice_line_id=None,
            three_pl_invoice_line_id=line.id,
            summary=(
                f"3PL {line.charge_type} rate on invoice {line.invoice_number} "
                f"exceeds the matched rate card."
            ),
            evidence_json={
                "invoice_number": line.invoice_number,
                "charge_type": line.charge_type,
                "quantity": quantity,
                "actual_unit_rate": _decimal_text(actual_unit_rate),
                "expected_unit_rate": _decimal_text(matched_rule.expected_rate),
                "amount": _decimal_text(line.amount),
                "raw_row_ref": line.raw_row_ref,
                "rate_card_rule_id": matched_rule.id,
            },
        )


def _detect_orphan_three_pl_invoice_lines(
    three_pl_lines: list[ThreePLInvoiceLine],
    shipments: dict[str, Shipment],
    rate_card_rules: list[RateCardRule],
) -> Iterable[IssueCandidate]:
    provider_name = _resolve_three_pl_provider_name(rate_card_rules)
    shipped_order_ids = {
        shipment.order_id
        for shipment in shipments.values()
        if shipment.order_id is not None
    }

    for line in three_pl_lines:
        if line.order_id is not None and line.order_id in shipped_order_ids:
            continue

        yield IssueCandidate(
            issue_type="invoice_line_without_matched_order_or_shipment",
            provider_name=provider_name,
            severity="high",
            status=ISSUE_STATUS_OPEN,
            confidence=Decimal("0.9950"),
            estimated_recoverable_amount=line.amount,
            shipment_id=None,
            parcel_invoice_line_id=None,
            three_pl_invoice_line_id=line.id,
            summary=(
                f"3PL invoice line on invoice {line.invoice_number} could not be "
                f"matched to both an order and shipment context."
            ),
            evidence_json={
                "invoice_number": line.invoice_number,
                "charge_type": line.charge_type,
                "order_id": line.order_id,
                "warehouse_id": line.warehouse_id,
                "amount": _decimal_text(line.amount),
                "raw_row_ref": line.raw_row_ref,
            },
        )


def _expected_parcel_rate(
    rate_card_rules: list[RateCardRule],
    *,
    provider_name: str,
    charge_type: str,
    invoice_date: date,
    service_level: str | None,
    zone: str | None,
    billed_weight_lb: Decimal | None,
) -> Decimal | None:
    matched_rule = _find_rate_card_rule(
        rate_card_rules,
        provider_type=PARCEL_PROVIDER_TYPE,
        provider_name=provider_name,
        charge_type=charge_type,
        invoice_date=invoice_date,
        service_level=service_level,
        zone=_parse_int(zone),
        weight_lb=billed_weight_lb,
    )
    if matched_rule is None:
        return None
    return matched_rule.expected_rate


def _has_parcel_contract_reference(
    rate_card_rules: list[RateCardRule],
    *,
    provider_name: str,
    charge_type: str,
    invoice_date: date,
    service_level: str | None,
) -> bool:
    for rule in rate_card_rules:
        if rule.provider_type != PARCEL_PROVIDER_TYPE:
            continue
        if rule.provider_name != provider_name:
            continue
        if rule.charge_type != charge_type:
            continue
        if rule.effective_start is not None and invoice_date < rule.effective_start:
            continue
        if rule.effective_end is not None and invoice_date > rule.effective_end:
            continue
        if not _matches_text_dimension(rule.service_level, service_level):
            continue
        return True
    return False


def _find_rate_card_rule(
    rate_card_rules: list[RateCardRule],
    *,
    provider_type: str,
    provider_name: str | None,
    charge_type: str,
    invoice_date: date,
    service_level: str | None,
    zone: int | None,
    weight_lb: Decimal | None,
) -> RateCardRule | None:
    matching_rules: list[RateCardRule] = []

    for rule in rate_card_rules:
        if rule.provider_type != provider_type:
            continue
        if provider_name is not None and rule.provider_name != provider_name:
            continue
        if rule.charge_type != charge_type:
            continue
        if rule.effective_start is not None and invoice_date < rule.effective_start:
            continue
        if rule.effective_end is not None and invoice_date > rule.effective_end:
            continue
        if not _matches_text_dimension(rule.service_level, service_level):
            continue
        if not _matches_numeric_range(zone, rule.zone_min, rule.zone_max):
            continue
        if not _matches_decimal_range(
            weight_lb, rule.weight_min_lb, rule.weight_max_lb
        ):
            continue
        matching_rules.append(rule)

    if not matching_rules:
        return None

    return sorted(
        matching_rules,
        key=lambda rule: (
            1 if rule.service_level else 0,
            1 if rule.zone_min is not None or rule.zone_max is not None else 0,
            1
            if rule.weight_min_lb is not None or rule.weight_max_lb is not None
            else 0,
            rule.effective_start or date.min,
            rule.id,
        ),
        reverse=True,
    )[0]


def _matches_text_dimension(
    rule_value: str | None, candidate_value: str | None
) -> bool:
    normalized_rule_value = _normalized_text(rule_value)
    if normalized_rule_value is None:
        return True
    normalized_candidate_value = _normalized_text(candidate_value)
    if normalized_candidate_value is None:
        return False
    return normalized_rule_value == normalized_candidate_value


def _matches_numeric_range(
    value: int | None, minimum: int | None, maximum: int | None
) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _matches_decimal_range(
    value: Decimal | None,
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _can_attempt_parcel_rate_lookup(line: ParcelInvoiceLine) -> bool:
    if line.charge_type != "transportation":
        return True
    return (
        line.service_level_billed is not None
        and line.zone_billed is not None
        and line.billed_weight_lb is not None
    )


def _expected_billable_weight(shipment: Shipment) -> Decimal | None:
    candidate_weights = [
        weight
        for weight in (shipment.weight_lb, shipment.dim_weight_lb)
        if weight is not None
    ]
    if not candidate_weights:
        return None
    maximum_weight = max(candidate_weights)
    rounded_weight = (maximum_weight * Decimal("2")).to_integral_value(
        rounding=ROUND_CEILING
    ) / Decimal("2")
    return rounded_weight.quantize(Decimal("0.01"))


def _actual_three_pl_unit_rate(line: ThreePLInvoiceLine) -> Decimal | None:
    if line.unit_rate is not None:
        return line.unit_rate
    if line.quantity is None or line.quantity <= 0:
        return None
    return _quantize_money(line.amount / Decimal(line.quantity))


def _resolve_three_pl_provider_name(rate_card_rules: list[RateCardRule]) -> str:
    provider_names = sorted(
        {
            rule.provider_name
            for rule in rate_card_rules
            if rule.provider_type == THREE_PL_PROVIDER_TYPE and rule.provider_name
        }
    )
    if len(provider_names) == 1:
        return provider_names[0]
    return THREE_PL_FALLBACK_PROVIDER_NAME


def _issue_identity_key(issue: RecoveryIssue) -> tuple[str, str, str, str]:
    return (
        issue.issue_type,
        issue.shipment_id or "",
        issue.parcel_invoice_line_id or "",
        issue.three_pl_invoice_line_id or "",
    )


def _issue_matches_candidate(issue: RecoveryIssue, candidate: IssueCandidate) -> bool:
    return (
        issue.provider_name == candidate.provider_name
        and issue.severity == candidate.severity
        and issue.status == candidate.status
        and issue.confidence == candidate.confidence
        and issue.estimated_recoverable_amount == candidate.estimated_recoverable_amount
        and issue.summary == candidate.summary
        and issue.evidence_json == candidate.evidence_json
    )


def _existing_issue_sort_key(issue: RecoveryIssue) -> tuple[date, str]:
    detected_at = (
        issue.detected_at.date() if issue.detected_at is not None else date.min
    )
    return (detected_at, issue.id)


def _parcel_line_sort_key(line: ParcelInvoiceLine) -> tuple[str, str]:
    return (line.raw_row_ref or "", line.id)


def _three_pl_line_sort_key(line: ThreePLInvoiceLine) -> tuple[str, str]:
    return (line.raw_row_ref or "", line.id)


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _service_level_rank(service_level: str | None) -> int | None:
    normalized = _normalized_text(service_level)
    if normalized is None:
        return None
    return SERVICE_LEVEL_RANKS.get(normalized)


def _parse_int(value: str | None) -> int | None:
    normalized = _normalized_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def _positive_difference(
    actual_value: Decimal,
    expected_value: Decimal | None,
) -> Decimal | None:
    if expected_value is None:
        return None
    difference = _quantize_money(actual_value - expected_value)
    if difference <= Decimal("0.00"):
        return None
    return difference


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.01'))}"


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
