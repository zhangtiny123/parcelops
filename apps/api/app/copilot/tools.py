from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import re
from typing import Optional, Union

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.issue_dashboard import get_issue_dashboard_summary
from app.models.billing import ParcelInvoiceLine
from app.models.fulfillment import OrderRecord, Shipment
from app.models.recovery import RecoveryIssue
from app.models.common import utcnow
from app.recovery_cases import (
    RecoveryCaseValidationError,
    build_case_draft,
    format_currency,
    format_status_label,
    money_or_zero,
)

from .types import Reference, ToolDefinition, ToolExecutionResult


@dataclass
class CopilotToolbox:
    db: Session

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_dashboard_metrics",
                description="Read issue dashboard totals, provider metrics, type metrics, and recent trends.",
            ),
            ToolDefinition(
                name="search_issues",
                description="Search and rank recovery issues by filters such as status, severity, confidence, provider, or amount.",
            ),
            ToolDefinition(
                name="get_issue_detail",
                description="Load one recovery issue with evidence and linked record identifiers.",
            ),
            ToolDefinition(
                name="lookup_shipment",
                description="Lookup a shipment by shipment id, external shipment id, or tracking number.",
            ),
            ToolDefinition(
                name="create_case_draft",
                description="Build a recovery case draft preview from one or more issue ids without persisting it.",
            ),
        ]

    def execute(self, name: str, arguments: dict[str, object]) -> ToolExecutionResult:
        handler_name = f"_tool_{name}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            raise ValueError(f"Unsupported copilot tool: {name}")
        return handler(arguments)

    def _tool_get_dashboard_metrics(
        self,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        days = _coerce_int(arguments.get("days"), default=30, minimum=1, maximum=365)
        compare_previous_period = bool(arguments.get("compare_previous_period", False))
        dashboard = get_issue_dashboard_summary(self.db, trend_days=days)

        output: dict[str, object] = {
            "days": days,
            "total_issue_count": dashboard.total_issue_count,
            "total_recoverable_amount": dashboard.total_recoverable_amount,
            "top_providers": [
                {
                    "provider_name": metric.name,
                    "issue_count": metric.count,
                    "estimated_recoverable_amount": metric.estimated_recoverable_amount,
                }
                for metric in dashboard.issues_by_provider[:5]
            ],
            "top_issue_types": [
                {
                    "issue_type": metric.name,
                    "issue_count": metric.count,
                    "estimated_recoverable_amount": metric.estimated_recoverable_amount,
                }
                for metric in dashboard.issues_by_type[:5]
            ],
            "trend": [
                {
                    "date": point.date,
                    "issue_count": point.count,
                    "estimated_recoverable_amount": point.estimated_recoverable_amount,
                }
                for point in dashboard.trend
            ],
        }

        if compare_previous_period:
            output["provider_period_deltas"] = self._calculate_provider_period_deltas(
                days
            )

        return ToolExecutionResult(
            name="get_dashboard_metrics",
            arguments={
                "days": days,
                "compare_previous_period": compare_previous_period,
            },
            output=output,
        )

    def _tool_search_issues(self, arguments: dict[str, object]) -> ToolExecutionResult:
        statement = select(RecoveryIssue)
        status_value = _coerce_optional_str(arguments.get("status"))
        severity = _coerce_optional_str(arguments.get("severity"))
        provider_name = _coerce_optional_str(arguments.get("provider_name"))
        issue_type = _coerce_optional_str(arguments.get("issue_type"))
        shipment_id = _coerce_optional_str(arguments.get("shipment_id"))
        min_confidence = _coerce_decimal(arguments.get("min_confidence"))
        query = _coerce_optional_str(arguments.get("query"))
        limit = _coerce_int(arguments.get("limit"), default=5, minimum=1, maximum=20)
        sort_by = _coerce_optional_str(arguments.get("sort_by")) or "detected_at_desc"

        if status_value is not None:
            statement = statement.where(RecoveryIssue.status == status_value)
        if severity is not None:
            statement = statement.where(RecoveryIssue.severity == severity)
        if provider_name is not None:
            statement = statement.where(
                func.lower(RecoveryIssue.provider_name) == provider_name.lower()
            )
        if issue_type is not None:
            statement = statement.where(RecoveryIssue.issue_type == issue_type)
        if shipment_id is not None:
            statement = statement.where(RecoveryIssue.shipment_id == shipment_id)
        if min_confidence is not None:
            statement = statement.where(RecoveryIssue.confidence >= min_confidence)
        if query is not None:
            query_terms = _search_terms(query)
            if query_terms:
                predicates = []
                for term in query_terms:
                    pattern = f"%{term}%"
                    predicates.extend(
                        [
                            func.lower(RecoveryIssue.summary).like(pattern),
                            func.lower(RecoveryIssue.issue_type).like(pattern),
                            func.lower(RecoveryIssue.provider_name).like(pattern),
                        ]
                    )
                statement = statement.where(or_(*predicates))

        amount_missing_rank = case(
            (RecoveryIssue.estimated_recoverable_amount.is_(None), 1),
            else_=0,
        )
        confidence_missing_rank = case(
            (RecoveryIssue.confidence.is_(None), 1),
            else_=0,
        )
        if sort_by == "recoverable_amount_desc":
            statement = statement.order_by(
                amount_missing_rank.asc(),
                RecoveryIssue.estimated_recoverable_amount.desc(),
                confidence_missing_rank.asc(),
                RecoveryIssue.confidence.desc(),
                RecoveryIssue.detected_at.desc(),
                RecoveryIssue.id.desc(),
            )
        elif sort_by == "confidence_desc":
            statement = statement.order_by(
                confidence_missing_rank.asc(),
                RecoveryIssue.confidence.desc(),
                amount_missing_rank.asc(),
                RecoveryIssue.estimated_recoverable_amount.desc(),
                RecoveryIssue.detected_at.desc(),
                RecoveryIssue.id.desc(),
            )
        else:
            statement = statement.order_by(
                RecoveryIssue.detected_at.desc(),
                RecoveryIssue.id.desc(),
            )

        issues = list(self.db.scalars(statement.limit(limit)))
        return ToolExecutionResult(
            name="search_issues",
            arguments={
                "status": status_value,
                "severity": severity,
                "provider_name": provider_name,
                "issue_type": issue_type,
                "shipment_id": shipment_id,
                "min_confidence": min_confidence,
                "query": query,
                "limit": limit,
                "sort_by": sort_by,
            },
            output={
                "result_count": len(issues),
                "issues": [
                    self._serialize_issue(issue, include_evidence=True)
                    for issue in issues
                ],
            },
            references=[self._issue_reference(issue) for issue in issues],
        )

    def _tool_get_issue_detail(
        self, arguments: dict[str, object]
    ) -> ToolExecutionResult:
        issue_id = _coerce_optional_str(arguments.get("issue_id"))
        if issue_id is None:
            raise ValueError("get_issue_detail requires issue_id")

        issue = self.db.scalar(
            select(RecoveryIssue).where(RecoveryIssue.id == issue_id)
        )
        if issue is None:
            return ToolExecutionResult(
                name="get_issue_detail",
                arguments={"issue_id": issue_id},
                output={"found": False, "issue_id": issue_id},
            )

        references = [self._issue_reference(issue)]
        if issue.shipment_id:
            references.append(
                Reference(
                    kind="shipment",
                    id=issue.shipment_id,
                    label=f"Shipment {issue.shipment_id}",
                )
            )

        return ToolExecutionResult(
            name="get_issue_detail",
            arguments={"issue_id": issue_id},
            output={
                "found": True,
                "issue": self._serialize_issue(issue, include_evidence=True),
            },
            references=references,
        )

    def _tool_lookup_shipment(
        self, arguments: dict[str, object]
    ) -> ToolExecutionResult:
        identifier = _coerce_optional_str(arguments.get("identifier"))
        if identifier is None:
            raise ValueError("lookup_shipment requires identifier")

        shipment = self.db.scalar(
            select(Shipment).where(
                or_(
                    Shipment.id == identifier,
                    Shipment.external_shipment_id == identifier,
                    Shipment.tracking_number == identifier,
                )
            )
        )
        if shipment is None:
            return ToolExecutionResult(
                name="lookup_shipment",
                arguments={"identifier": identifier},
                output={"found": False, "identifier": identifier},
            )

        order = (
            self.db.get(OrderRecord, shipment.order_id) if shipment.order_id else None
        )
        linked_issues = list(
            self.db.scalars(
                select(RecoveryIssue)
                .where(RecoveryIssue.shipment_id == shipment.id)
                .order_by(RecoveryIssue.detected_at.desc(), RecoveryIssue.id.desc())
            )
        )
        parcel_invoice_lines = list(
            self.db.scalars(
                select(ParcelInvoiceLine)
                .where(ParcelInvoiceLine.shipment_id == shipment.id)
                .order_by(
                    ParcelInvoiceLine.invoice_date.desc(),
                    ParcelInvoiceLine.id.desc(),
                )
                .limit(5)
            )
        )

        references = [
            Reference(
                kind="shipment",
                id=shipment.id,
                label=f"Shipment {shipment.id}",
                detail=shipment.tracking_number,
            )
        ]
        references.extend(self._issue_reference(issue) for issue in linked_issues)

        return ToolExecutionResult(
            name="lookup_shipment",
            arguments={"identifier": identifier},
            output={
                "found": True,
                "shipment": {
                    "id": shipment.id,
                    "external_shipment_id": shipment.external_shipment_id,
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                    "service_level": shipment.service_level,
                    "origin_zip": shipment.origin_zip,
                    "destination_zip": shipment.destination_zip,
                    "zone": shipment.zone,
                    "weight_lb": shipment.weight_lb,
                    "dim_weight_lb": shipment.dim_weight_lb,
                    "shipped_at": shipment.shipped_at,
                    "delivered_at": shipment.delivered_at,
                    "warehouse_id": shipment.warehouse_id,
                },
                "order": (
                    {
                        "id": order.id,
                        "external_order_id": order.external_order_id,
                        "customer_ref": order.customer_ref,
                        "promised_service_level": order.promised_service_level,
                        "warehouse_id": order.warehouse_id,
                    }
                    if order is not None
                    else None
                ),
                "linked_issues": [
                    self._serialize_issue(issue, include_evidence=False)
                    for issue in linked_issues
                ],
                "parcel_invoice_lines": [
                    {
                        "id": line.id,
                        "invoice_number": line.invoice_number,
                        "invoice_date": line.invoice_date,
                        "charge_type": line.charge_type,
                        "amount": line.amount,
                        "currency": line.currency,
                    }
                    for line in parcel_invoice_lines
                ],
            },
            references=references,
        )

    def _tool_create_case_draft(
        self,
        arguments: dict[str, object],
    ) -> ToolExecutionResult:
        raw_issue_ids = arguments.get("issue_ids")
        if not isinstance(raw_issue_ids, list):
            raise ValueError("create_case_draft requires issue_ids")

        issue_ids = [str(issue_id) for issue_id in raw_issue_ids]
        title = _coerce_optional_str(arguments.get("title"))

        try:
            case_draft = build_case_draft(issue_ids, self.db, title=title)
        except RecoveryCaseValidationError as exc:
            return ToolExecutionResult(
                name="create_case_draft",
                arguments={"issue_ids": issue_ids, "title": title},
                output={
                    "created": False,
                    "persisted": False,
                    "error": str(exc),
                },
            )

        return ToolExecutionResult(
            name="create_case_draft",
            arguments={"issue_ids": case_draft.issue_ids, "title": title},
            output={
                "created": True,
                "persisted": False,
                "title": case_draft.title,
                "issue_count": len(case_draft.issues),
                "issue_ids": case_draft.issue_ids,
                "estimated_recoverable_amount": case_draft.estimated_recoverable_amount,
                "estimated_recoverable_amount_display": format_currency(
                    case_draft.estimated_recoverable_amount
                ),
                "draft_summary": case_draft.draft_summary,
                "draft_email": case_draft.draft_email,
            },
            references=[self._issue_reference(issue) for issue in case_draft.issues],
        )

    def _calculate_provider_period_deltas(self, days: int) -> list[dict[str, object]]:
        today = utcnow().date()
        current_start_day = today - timedelta(days=days - 1)
        current_start = datetime.combine(
            current_start_day,
            time.min,
            tzinfo=timezone.utc,
        )
        previous_start = current_start - timedelta(days=days)

        provider_amount_expr = func.sum(
            RecoveryIssue.estimated_recoverable_amount
        ).label("estimated_recoverable_amount")
        provider_count_expr = func.count(RecoveryIssue.id).label("issue_count")
        bucket_expr = case(
            (RecoveryIssue.detected_at >= current_start, "current"),
            else_="previous",
        ).label("bucket")

        statement = (
            select(
                RecoveryIssue.provider_name.label("provider_name"),
                bucket_expr,
                provider_count_expr,
                provider_amount_expr,
            )
            .where(RecoveryIssue.detected_at >= previous_start)
            .group_by(RecoveryIssue.provider_name, bucket_expr)
        )

        period_totals: dict[str, dict[str, dict[str, Union[Decimal, int]]]] = {}
        for row in self.db.execute(statement).all():
            provider_totals = period_totals.setdefault(
                row.provider_name,
                {
                    "current": {
                        "issue_count": 0,
                        "estimated_recoverable_amount": Decimal("0.00"),
                    },
                    "previous": {
                        "issue_count": 0,
                        "estimated_recoverable_amount": Decimal("0.00"),
                    },
                },
            )
            provider_totals[row.bucket] = {
                "issue_count": int(row.issue_count or 0),
                "estimated_recoverable_amount": money_or_zero(
                    row.estimated_recoverable_amount
                ),
            }

        rows: list[dict[str, object]] = []
        for provider_name, buckets in period_totals.items():
            current_amount = money_or_zero(
                buckets["current"]["estimated_recoverable_amount"]
            )
            previous_amount = money_or_zero(
                buckets["previous"]["estimated_recoverable_amount"]
            )
            rows.append(
                {
                    "provider_name": provider_name,
                    "current_issue_count": int(buckets["current"]["issue_count"]),
                    "previous_issue_count": int(buckets["previous"]["issue_count"]),
                    "current_recoverable_amount": current_amount,
                    "previous_recoverable_amount": previous_amount,
                    "recoverable_amount_delta": (
                        current_amount - previous_amount
                    ).quantize(Decimal("0.01")),
                }
            )

        rows.sort(
            key=lambda row: (
                money_or_zero(row["recoverable_amount_delta"]),
                money_or_zero(row["current_recoverable_amount"]),
            ),
            reverse=True,
        )
        return rows

    def _serialize_issue(
        self,
        issue: RecoveryIssue,
        *,
        include_evidence: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": issue.id,
            "issue_type": issue.issue_type,
            "issue_type_label": format_status_label(issue.issue_type),
            "provider_name": issue.provider_name,
            "severity": issue.severity,
            "status": issue.status,
            "confidence": issue.confidence,
            "estimated_recoverable_amount": issue.estimated_recoverable_amount,
            "estimated_recoverable_amount_display": format_currency(
                money_or_zero(issue.estimated_recoverable_amount)
            ),
            "shipment_id": issue.shipment_id,
            "parcel_invoice_line_id": issue.parcel_invoice_line_id,
            "three_pl_invoice_line_id": issue.three_pl_invoice_line_id,
            "summary": issue.summary,
            "detected_at": issue.detected_at,
        }
        if include_evidence:
            payload["evidence_json"] = issue.evidence_json
        return payload

    def _issue_reference(self, issue: RecoveryIssue) -> Reference:
        return Reference(
            kind="issue",
            id=issue.id,
            label=f"Issue {issue.id}",
            detail=issue.summary,
        )


def _coerce_decimal(value: object) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _coerce_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        coerced = int(value)
    elif isinstance(value, int):
        coerced = value
    elif isinstance(value, (float, Decimal, str)):
        coerced = int(value)
    else:
        return default

    return max(minimum, min(maximum, coerced))


def _coerce_optional_str(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _search_terms(query: str) -> list[str]:
    terms = [term for term in re.split(r"[^a-z0-9]+", query.lower()) if len(term) >= 3]
    return terms[:6]
