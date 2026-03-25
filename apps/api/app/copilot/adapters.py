from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import date
import re
from typing import Optional

from app.models.common import utcnow
from app.recovery_cases import format_currency, format_status_label

from .types import (
    AdapterPlan,
    ChatMessage,
    CopilotAnswer,
    Reference,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionResult,
)

SUPPORTED_PROVIDER_NAMES = {"heuristic"}


class CopilotConfigurationError(ValueError):
    """Raised when the configured copilot provider is unavailable."""


class LLMAdapter(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    def plan(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> AdapterPlan:
        raise NotImplementedError

    @abstractmethod
    def compose_answer(
        self,
        messages: list[ChatMessage],
        tool_results: list[ToolExecutionResult],
    ) -> CopilotAnswer:
        raise NotImplementedError


class HeuristicToolCallingAdapter(LLMAdapter):
    provider_name = "heuristic"
    model_name = "heuristic-tool-calling-v1"

    def plan(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> AdapterPlan:
        del tools

        user_message = _latest_user_message(messages)
        if user_message is None:
            return AdapterPlan(
                status="unsupported",
                refusal_message=(
                    "I need a user question before I can query ParcelOps data."
                ),
            )

        question = user_message.content.strip()
        lowered = question.lower()
        count_question = _looks_like_count_question(lowered)
        issue_ids = _extract_issue_ids(question)
        limit = _extract_limit(lowered)
        provider_name = _extract_provider_name(question)
        status_value = _extract_status(lowered)
        severity = _extract_severity(lowered)
        issue_type = _extract_issue_type(lowered)

        if _looks_like_case_draft(lowered):
            if not issue_ids:
                return AdapterPlan(
                    status="unsupported",
                    refusal_message=(
                        "I can draft a recovery case when you provide one or more issue IDs."
                    ),
                )
            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="create_case_draft",
                        arguments={
                            "issue_ids": issue_ids,
                            "title": _extract_case_title(question),
                        },
                    )
                ],
            )

        if issue_ids and _looks_like_issue_detail(lowered):
            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="get_issue_detail",
                        arguments={"issue_id": issue_id},
                    )
                    for issue_id in issue_ids[:5]
                ],
            )

        shipment_identifier = _extract_shipment_identifier(question)
        if _looks_like_shipment_search(lowered, shipment_identifier):
            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="search_shipments",
                        arguments={
                            "carrier": provider_name,
                            "intent": "count" if count_question else "search",
                            "limit": limit,
                        },
                    )
                ],
            )

        if _looks_like_shipment_lookup(lowered, shipment_identifier):
            if shipment_identifier is None:
                return AdapterPlan(
                    status="unsupported",
                    refusal_message=(
                        "I can look up a shipment if you provide a shipment ID, external shipment ID, or tracking number."
                    ),
                )
            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="lookup_shipment",
                        arguments={"identifier": shipment_identifier},
                    )
                ],
            )

        if _looks_like_issue_search(lowered):
            sort_by = "detected_at_desc"
            intent = "count" if count_question else "search"
            min_confidence = None
            if _looks_like_top_recovery_question(lowered):
                intent = "top_recovery"
                sort_by = "recoverable_amount_desc"
                status_value = status_value or "open"
            if _looks_like_high_confidence_question(lowered):
                if not count_question:
                    intent = "high_confidence"
                sort_by = "confidence_desc"
                status_value = status_value or "open"
                min_confidence = "0.80"

            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="search_issues",
                        arguments={
                            "intent": intent,
                            "status": status_value,
                            "severity": severity,
                            "provider_name": provider_name,
                            "issue_type": issue_type,
                            "limit": limit,
                            "sort_by": sort_by,
                            "min_confidence": min_confidence,
                        },
                    )
                ],
            )

        if _looks_like_dashboard_question(lowered):
            days = _extract_days(lowered)
            compare_previous_period = _looks_like_period_comparison(lowered)
            return AdapterPlan(
                status="completed",
                tool_calls=[
                    ToolCallRequest(
                        name="get_dashboard_metrics",
                        arguments={
                            "days": days,
                            "compare_previous_period": compare_previous_period,
                        },
                    )
                ],
            )

        return AdapterPlan(
            status="unsupported",
            refusal_message=(
                "I can only answer grounded questions about ParcelOps dashboard metrics, recovery issues, shipments, and recovery case drafts."
            ),
        )

    def compose_answer(
        self,
        messages: list[ChatMessage],
        tool_results: list[ToolExecutionResult],
    ) -> CopilotAnswer:
        del messages

        response_sections: list[str] = []
        references: list[Reference] = []
        for tool_result in tool_results:
            response_sections.append(self._format_tool_result(tool_result))
            references.extend(tool_result.references)

        return CopilotAnswer(
            status="completed",
            message="\n\n".join(section for section in response_sections if section),
            references=_dedupe_references(references),
        )

    def _format_tool_result(self, tool_result: ToolExecutionResult) -> str:
        if tool_result.name == "get_dashboard_metrics":
            return self._format_dashboard(tool_result.output)
        if tool_result.name == "search_issues":
            return self._format_issue_search(tool_result)
        if tool_result.name == "get_issue_detail":
            return self._format_issue_detail(tool_result.output)
        if tool_result.name == "lookup_shipment":
            return self._format_shipment_lookup(tool_result.output)
        if tool_result.name == "search_shipments":
            return self._format_shipment_search(tool_result)
        if tool_result.name == "create_case_draft":
            return self._format_case_draft(tool_result.output)
        raise ValueError(f"Unsupported tool result formatter: {tool_result.name}")

    def _format_dashboard(self, output: dict[str, object]) -> str:
        days = _read_int(output, "days")
        lines = [
            (
                f"In the last {days} days, ParcelOps has "
                f"{_read_int(output, 'total_issue_count')} recovery issue(s) totaling "
                f"{format_currency(_read_decimal(output, 'total_recoverable_amount'))}."
            )
        ]

        top_providers = _read_dict_list(output, "top_providers")
        if top_providers:
            provider_summary = "; ".join(
                (
                    f"{_read_str(provider, 'provider_name')}: "
                    f"{format_currency(_read_decimal(provider, 'estimated_recoverable_amount'))} "
                    f"across {_read_int(provider, 'issue_count')} issue(s)"
                )
                for provider in top_providers[:3]
            )
            lines.append(f"Top providers: {provider_summary}.")

        top_issue_types = _read_dict_list(output, "top_issue_types")
        if top_issue_types:
            type_summary = "; ".join(
                (
                    f"{format_status_label(_read_str(issue_type, 'issue_type'))}: "
                    f"{_read_int(issue_type, 'issue_count')} issue(s)"
                )
                for issue_type in top_issue_types[:3]
            )
            lines.append(f"Top issue types: {type_summary}.")

        provider_period_deltas = _read_dict_list(output, "provider_period_deltas")
        if provider_period_deltas:
            positive_deltas = [
                row
                for row in provider_period_deltas
                if _read_decimal(row, "recoverable_amount_delta") > 0
            ]
            if positive_deltas:
                delta_summary = "; ".join(
                    (
                        f"{_read_str(row, 'provider_name')} increased by "
                        f"{format_currency(_read_decimal(row, 'recoverable_amount_delta'))}"
                    )
                    for row in positive_deltas[:3]
                )
                lines.append(
                    "Compared with the previous matching time window, the sharpest increases are: "
                    + delta_summary
                    + "."
                )
            else:
                lines.append(
                    "Compared with the previous matching time window, no provider shows a positive recoverable-amount increase."
                )

        return " ".join(lines)

    def _format_issue_search(self, tool_result: ToolExecutionResult) -> str:
        arguments = tool_result.arguments
        output = tool_result.output
        intent = _read_str(arguments, "intent") or "search"
        issues = _read_dict_list(output, "issues")
        total_count = _read_int(output, "total_count")
        filter_suffix = _format_issue_filter_suffix(arguments)

        if total_count == 0:
            return "I did not find any recovery issues that match that request."

        if intent == "count":
            return f"ParcelOps currently has {total_count} recovery issue(s){filter_suffix}."

        issue_lines = [
            (
                f"{_read_str(issue, 'id')}: {_read_str(issue, 'issue_type_label')} with {_read_str(issue, 'provider_name')} "
                f"[{_read_str(issue, 'severity')}/{_read_str(issue, 'status')}] estimated "
                f"{_read_str(issue, 'estimated_recoverable_amount_display')}. {_read_str(issue, 'summary')}"
            )
            for issue in issues[:5]
        ]

        if intent == "top_recovery":
            return (
                f"I found {total_count} matching recovery issue(s){filter_suffix}. "
                "The highest recoverable matches are: " + " ".join(issue_lines)
            )

        if intent == "high_confidence":
            return (
                f"I found {total_count} high-confidence recovery issue(s){filter_suffix}. "
                "The strongest matches are: " + " ".join(issue_lines)
            )

        return (
            f"I found {total_count} matching recovery issue(s){filter_suffix}. "
            + " ".join(issue_lines)
        )

    def _format_issue_detail(self, output: dict[str, object]) -> str:
        if not _read_bool(output, "found"):
            return f"I could not find recovery issue {_read_str(output, 'issue_id')}."

        issue = _read_dict(output, "issue")
        evidence_json = _read_dict(issue, "evidence_json")
        evidence_summary = ", ".join(
            f"{key}={value}" for key, value in sorted(evidence_json.items())
        )
        lines = [
            (
                f"{_read_str(issue, 'id')} is a {_read_str(issue, 'issue_type_label')} issue with {_read_str(issue, 'provider_name')} "
                f"[{_read_str(issue, 'severity')}/{_read_str(issue, 'status')}]. Estimated recoverable amount: "
                f"{_read_str(issue, 'estimated_recoverable_amount_display')}."
            ),
            _read_str(issue, "summary"),
        ]
        if issue.get("confidence") is not None:
            lines.append(f"Confidence: {issue['confidence']}.")
        if evidence_summary:
            lines.append(f"Evidence: {evidence_summary}.")
        return " ".join(lines)

    def _format_shipment_lookup(self, output: dict[str, object]) -> str:
        if not _read_bool(output, "found"):
            return f"I could not find a shipment for {_read_str(output, 'identifier')}."

        shipment = _read_dict(output, "shipment")
        lines = [
            (
                f"Shipment {_read_str(shipment, 'id')} tracks as {_read_str(shipment, 'tracking_number')} with "
                f"{_read_str(shipment, 'carrier')} {_read_str(shipment, 'service_level') or 'service'}."
            )
        ]
        if shipment.get("shipped_at"):
            lines.append(f"Shipped at {shipment['shipped_at']}.")
        if shipment.get("delivered_at"):
            lines.append(f"Delivered at {shipment['delivered_at']}.")

        linked_issues = _read_dict_list(output, "linked_issues")
        if linked_issues:
            issue_summary = "; ".join(
                f"{_read_str(issue, 'id')} ({_read_str(issue, 'issue_type_label')}, {_read_str(issue, 'estimated_recoverable_amount_display')})"
                for issue in linked_issues[:3]
            )
            lines.append(f"Linked recovery issues: {issue_summary}.")
        else:
            lines.append("There are no linked recovery issues for this shipment.")

        parcel_invoice_lines = _read_dict_list(output, "parcel_invoice_lines")
        if parcel_invoice_lines:
            invoice_summary = "; ".join(
                f"{_read_str(line, 'invoice_number')} {_read_str(line, 'charge_type')} "
                f"{format_currency(_read_decimal(line, 'amount'))}"
                for line in parcel_invoice_lines[:3]
            )
            lines.append(f"Recent parcel invoice lines: {invoice_summary}.")

        return " ".join(lines)

    def _format_shipment_search(self, tool_result: ToolExecutionResult) -> str:
        arguments = tool_result.arguments
        output = tool_result.output
        total_count = _read_int(output, "total_count")
        intent = _read_str(arguments, "intent") or "search"
        carrier = _read_str(arguments, "carrier")
        carrier_suffix = f" for carrier {carrier}" if carrier else ""

        if total_count == 0:
            return f"I did not find any shipment records{carrier_suffix}."

        if intent == "count":
            return f"ParcelOps currently has {total_count} shipment record(s){carrier_suffix}."

        shipments = _read_dict_list(output, "shipments")
        shipment_lines = [
            (
                f"{_read_str(shipment, 'id')} tracking {_read_str(shipment, 'tracking_number')} "
                f"with {_read_str(shipment, 'carrier')} {_read_str(shipment, 'service_level') or 'service'}"
            )
            for shipment in shipments[:5]
        ]
        return (
            f"I found {total_count} shipment record(s){carrier_suffix}. "
            "The latest matches are: " + "; ".join(shipment_lines) + "."
        )

    def _format_case_draft(self, output: dict[str, object]) -> str:
        if not _read_bool(output, "created"):
            return "I could not build that recovery case draft safely. " + str(
                output.get("error", "Unknown validation error.")
            )

        return (
            f'I prepared a recovery case draft titled "{_read_str(output, "title")}" for '
            f"{_read_int(output, 'issue_count')} issue(s) totaling {_read_str(output, 'estimated_recoverable_amount_display')}. "
            "This is a preview only and has not been persisted. "
            f"Case summary:\n{_read_str(output, 'draft_summary')}\n\n"
            f"Dispute email draft:\n{_read_str(output, 'draft_email')}\n\n"
            f"Internal next-step note:\n{_read_str(output, 'draft_internal_note')}"
        )


def get_llm_adapter(provider_name: str) -> LLMAdapter:
    normalized_provider_name = provider_name.strip().lower()
    if normalized_provider_name == "heuristic":
        return HeuristicToolCallingAdapter()
    raise CopilotConfigurationError(
        f"Unsupported copilot provider '{provider_name}'. Supported providers: heuristic."
    )


def _latest_user_message(messages: list[ChatMessage]) -> Optional[ChatMessage]:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message
    return None


def _looks_like_case_draft(lowered: str) -> bool:
    return (
        "case draft" in lowered or "draft case" in lowered or "draft dispute" in lowered
    )


def _looks_like_issue_detail(lowered: str) -> bool:
    issue_detail_markers = (
        "issue",
        "issues",
        "detail",
        "details",
        "evidence",
        "show",
        "explain",
        "tell me",
    )
    return any(marker in lowered for marker in issue_detail_markers)


def _looks_like_shipment_lookup(
    lowered: str,
    shipment_identifier: Optional[str],
) -> bool:
    if shipment_identifier is not None:
        return True
    markers = (
        "look up shipment",
        "lookup shipment",
        "find shipment",
        "show shipment",
        "shipment detail",
        "shipment details",
        "tracking",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_shipment_search(
    lowered: str,
    shipment_identifier: Optional[str],
) -> bool:
    if shipment_identifier is not None:
        return False

    if "shipment" not in lowered and "shipments" not in lowered:
        return False

    markers = (
        "shipment records",
        "list shipments",
        "show shipments",
        "latest shipments",
    )
    return _looks_like_count_question(lowered) or any(
        marker in lowered for marker in markers
    )


def _looks_like_dashboard_question(lowered: str) -> bool:
    markers = (
        "dashboard",
        "metric",
        "metrics",
        "trend",
        "increase",
        "recoverable amount",
        "recovery-cost",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_issue_search(lowered: str) -> bool:
    markers = (
        "issue",
        "issues",
        "error",
        "errors",
        "recovery",
        "recoveries",
        "high confidence",
        "top recover",
        "highest recoverable",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_count_question(lowered: str) -> bool:
    markers = (
        "how many",
        "count",
        "number of",
        "total ",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_high_confidence_question(lowered: str) -> bool:
    markers = (
        "high confidence",
        "highest-confidence",
        "highest confidence",
        "strongest confidence",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_top_recovery_question(lowered: str) -> bool:
    markers = (
        "top recover",
        "highest recoverable",
        "largest recoverable",
        "highest amount",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_period_comparison(lowered: str) -> bool:
    return "increase" in lowered or "compare" in lowered or "previous" in lowered


def _extract_issue_ids(text: str) -> list[str]:
    seen_issue_ids: set[str] = set()
    issue_ids: list[str] = []
    for issue_id in re.findall(r"\bissue-[a-z0-9_-]+\b", text, flags=re.IGNORECASE):
        normalized_issue_id = issue_id.lower()
        if normalized_issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(normalized_issue_id)
        issue_ids.append(normalized_issue_id)
    return issue_ids


def _extract_limit(lowered: str) -> int:
    match = re.search(r"\btop\s+(\d+)\b", lowered)
    if match is None:
        match = re.search(r"\b(\d+)\s+(?:issues|errors|recoveries)\b", lowered)
    if match is None:
        return 5
    return max(1, min(10, int(match.group(1))))


def _extract_provider_name(text: str) -> Optional[str]:
    provider_names = ("UPS", "FedEx", "USPS", "DHL")
    lowered = text.lower()
    for provider_name in provider_names:
        if provider_name.lower() in lowered:
            return provider_name
    return None


def _extract_status(lowered: str) -> Optional[str]:
    for status_value in ("open", "pending", "resolved"):
        if re.search(rf"\b{status_value}\b", lowered):
            return status_value
    return None


def _extract_severity(lowered: str) -> Optional[str]:
    for severity in ("high", "medium", "low"):
        if re.search(rf"\b{severity}\b", lowered):
            return severity
    return None


def _extract_issue_type(lowered: str) -> Optional[str]:
    issue_type_patterns = (
        ("duplicate charge", "duplicate_charge"),
        ("duplicate charges", "duplicate_charge"),
        ("weight mismatch", "billed_weight_mismatch"),
        ("billed weight", "billed_weight_mismatch"),
    )
    for marker, issue_type in issue_type_patterns:
        if marker in lowered:
            return issue_type
    return None


def _extract_days(lowered: str) -> int:
    match = re.search(r"\b(?:last|past)\s+(\d+)\s+days?\b", lowered)
    if match is not None:
        return max(1, min(365, int(match.group(1))))

    if "this month" in lowered:
        today = utcnow().date()
        start_of_month = date(today.year, today.month, 1)
        return (today - start_of_month).days + 1

    return 30


def _extract_shipment_identifier(text: str) -> Optional[str]:
    tracking_match = re.search(
        r"\b(?:tracking(?: number)?|shipment id|external shipment id)[:\s#-]*([A-Za-z0-9_-]{6,})\b",
        text,
        flags=re.IGNORECASE,
    )
    if tracking_match is not None:
        return tracking_match.group(1)

    for token in re.findall(r"\b[A-Za-z0-9_-]{6,}\b", text):
        if token.lower().startswith("issue-"):
            continue
        if token.lower().startswith("shipment-") or token.upper().startswith("1Z"):
            return token
    return None


def _extract_case_title(text: str) -> Optional[str]:
    quoted_title_match = re.search(r'title\s+"([^"]+)"', text, flags=re.IGNORECASE)
    if quoted_title_match is not None:
        return quoted_title_match.group(1).strip()
    return None


def _dedupe_references(references: list[Reference]) -> list[Reference]:
    deduped_references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str]] = set()
    for reference in references:
        reference_key = (reference.kind, reference.id)
        if reference_key in seen_reference_keys:
            continue
        seen_reference_keys.add(reference_key)
        deduped_references.append(reference)
    return deduped_references


def _format_issue_filter_suffix(arguments: dict[str, object]) -> str:
    filters: list[str] = []

    status_value = _read_str(arguments, "status")
    if status_value:
        filters.append(f"status={status_value}")

    severity = _read_str(arguments, "severity")
    if severity:
        filters.append(f"severity={severity}")

    provider_name = _read_str(arguments, "provider_name")
    if provider_name:
        filters.append(f"provider={provider_name}")

    issue_type = _read_str(arguments, "issue_type")
    if issue_type:
        filters.append(f"type={format_status_label(issue_type)}")

    shipment_id = _read_str(arguments, "shipment_id")
    if shipment_id:
        filters.append(f"shipment={shipment_id}")

    min_confidence = _read_str(arguments, "min_confidence")
    if min_confidence:
        filters.append(f"confidence>={min_confidence}")

    if not filters:
        return ""

    return " (" + ", ".join(filters) + ")"


def _read_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, bool) and value


def _read_decimal(payload: dict[str, object], key: str) -> Decimal:
    value = payload.get(key)
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _read_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _read_dict_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _read_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except Exception:
        return 0


def _read_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)
