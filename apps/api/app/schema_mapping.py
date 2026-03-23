from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing_extensions import Optional


SOURCE_KIND_SHIPMENT = "shipment"
SOURCE_KIND_PARCEL_INVOICE = "parcel_invoice"
SOURCE_KIND_SHIPMENT_EVENT = "shipment_event"
SOURCE_KIND_ORDER = "order"
SOURCE_KIND_THREE_PL_INVOICE = "three_pl_invoice"
SOURCE_KIND_RATE_CARD = "rate_card"

SOURCE_KIND_ORDERING = (
    SOURCE_KIND_SHIPMENT,
    SOURCE_KIND_PARCEL_INVOICE,
    SOURCE_KIND_SHIPMENT_EVENT,
    SOURCE_KIND_ORDER,
    SOURCE_KIND_THREE_PL_INVOICE,
    SOURCE_KIND_RATE_CARD,
)


@dataclass(frozen=True)
class CanonicalFieldDefinition:
    name: str
    label: str
    description: str
    required: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class MappingSuggestion:
    source_column: str
    canonical_field: str
    confidence: float
    reason: str


CANONICAL_FIELD_REGISTRY: dict[str, tuple[CanonicalFieldDefinition, ...]] = {
    SOURCE_KIND_SHIPMENT: (
        CanonicalFieldDefinition(
            "external_shipment_id",
            "External Shipment ID",
            "Carrier or warehouse shipment identifier from the raw file.",
            required=True,
            aliases=("shipment id", "shipment identifier", "shipment_id"),
        ),
        CanonicalFieldDefinition(
            "external_order_id",
            "External Order ID",
            "Order identifier from the source system.",
            aliases=("order id", "order identifier", "customer order id", "order_id"),
        ),
        CanonicalFieldDefinition(
            "tracking_number",
            "Tracking Number",
            "Parcel tracking number.",
            required=True,
            aliases=("tracking", "tracking #", "tracking no"),
        ),
        CanonicalFieldDefinition(
            "carrier",
            "Carrier",
            "Shipping carrier name.",
            required=True,
        ),
        CanonicalFieldDefinition(
            "service_level",
            "Service Level",
            "Service level promised or used for shipment.",
            aliases=("service", "shipping service"),
        ),
        CanonicalFieldDefinition(
            "origin_zip",
            "Origin ZIP",
            "Origin postal code.",
            aliases=("origin postal code", "ship from zip"),
        ),
        CanonicalFieldDefinition(
            "destination_zip",
            "Destination ZIP",
            "Destination postal code.",
            aliases=("destination postal code", "ship to zip"),
        ),
        CanonicalFieldDefinition("zone", "Zone", "Carrier billing zone."),
        CanonicalFieldDefinition(
            "weight_lb",
            "Weight (lb)",
            "Actual shipment weight in pounds.",
            aliases=("weight", "actual weight", "weight lbs"),
        ),
        CanonicalFieldDefinition(
            "dim_weight_lb",
            "DIM Weight (lb)",
            "Dimensional weight in pounds.",
            aliases=("dim weight", "dimensional weight"),
        ),
        CanonicalFieldDefinition(
            "shipped_at",
            "Shipped At",
            "Timestamp when the shipment was shipped.",
            aliases=("ship date", "shipped date"),
        ),
        CanonicalFieldDefinition(
            "delivered_at",
            "Delivered At",
            "Timestamp when the shipment was delivered.",
            aliases=("delivery date", "delivered date"),
        ),
        CanonicalFieldDefinition(
            "warehouse_id",
            "Warehouse ID",
            "Warehouse or fulfillment center identifier.",
            aliases=("warehouse", "fulfillment center"),
        ),
    ),
    SOURCE_KIND_PARCEL_INVOICE: (
        CanonicalFieldDefinition(
            "invoice_number",
            "Invoice Number",
            "Carrier invoice number.",
            required=True,
            aliases=("invoice #", "invoice no"),
        ),
        CanonicalFieldDefinition(
            "invoice_date",
            "Invoice Date",
            "Carrier invoice date.",
            required=True,
        ),
        CanonicalFieldDefinition(
            "external_shipment_id",
            "External Shipment ID",
            "Shipment identifier from the source data.",
            aliases=("shipment id", "shipment identifier"),
        ),
        CanonicalFieldDefinition(
            "tracking_number",
            "Tracking Number",
            "Parcel tracking number.",
            required=True,
            aliases=("tracking", "tracking #", "tracking no"),
        ),
        CanonicalFieldDefinition(
            "carrier",
            "Carrier",
            "Carrier name for the billed shipment.",
            required=True,
        ),
        CanonicalFieldDefinition(
            "charge_type",
            "Charge Type",
            "Type of billed carrier charge.",
            required=True,
            aliases=("charge code", "fee type"),
        ),
        CanonicalFieldDefinition(
            "service_level_billed",
            "Service Level Billed",
            "Service level shown on the invoice.",
            aliases=("service billed", "service level"),
        ),
        CanonicalFieldDefinition(
            "billed_weight_lb",
            "Billed Weight (lb)",
            "Weight billed by the carrier in pounds.",
            aliases=("billed weight", "billable weight"),
        ),
        CanonicalFieldDefinition(
            "zone_billed",
            "Zone Billed",
            "Zone billed by the carrier.",
            aliases=("billed zone",),
        ),
        CanonicalFieldDefinition(
            "amount",
            "Amount",
            "Billed amount.",
            required=True,
            aliases=("charge amount", "invoice amount"),
        ),
        CanonicalFieldDefinition(
            "currency",
            "Currency",
            "Currency code for the billed amount.",
            aliases=("currency code",),
        ),
        CanonicalFieldDefinition(
            "raw_row_ref",
            "Raw Row Reference",
            "Traceability reference for the original row.",
            aliases=("row ref", "row reference"),
        ),
    ),
    SOURCE_KIND_SHIPMENT_EVENT: (
        CanonicalFieldDefinition(
            "external_shipment_id",
            "External Shipment ID",
            "Shipment identifier from the raw feed.",
            aliases=("shipment id", "shipment identifier"),
        ),
        CanonicalFieldDefinition(
            "tracking_number",
            "Tracking Number",
            "Parcel tracking number.",
            required=True,
            aliases=("tracking", "tracking #", "tracking no"),
        ),
        CanonicalFieldDefinition(
            "event_type",
            "Event Type",
            "Carrier or platform event name.",
            required=True,
            aliases=("status", "event", "tracking event"),
        ),
        CanonicalFieldDefinition(
            "event_time",
            "Event Time",
            "Timestamp for the event.",
            required=True,
            aliases=("event date", "event timestamp", "status time"),
        ),
        CanonicalFieldDefinition(
            "location",
            "Location",
            "Event location or scan city.",
            aliases=("scan location", "event location"),
        ),
        CanonicalFieldDefinition(
            "raw_row_ref",
            "Raw Row Reference",
            "Traceability reference for the original row.",
            aliases=("row ref", "row reference"),
        ),
    ),
    SOURCE_KIND_ORDER: (
        CanonicalFieldDefinition(
            "external_order_id",
            "External Order ID",
            "Order identifier from the commerce system.",
            required=True,
            aliases=("order id", "order identifier"),
        ),
        CanonicalFieldDefinition(
            "customer_ref",
            "Customer Reference",
            "Customer or account reference.",
            aliases=("customer id", "customer"),
        ),
        CanonicalFieldDefinition(
            "order_date",
            "Order Date",
            "Timestamp when the order was created.",
            required=True,
            aliases=("created at", "ordered at"),
        ),
        CanonicalFieldDefinition(
            "promised_service_level",
            "Promised Service Level",
            "Promised shipping or service level.",
            aliases=("service level", "promised shipping method"),
        ),
        CanonicalFieldDefinition(
            "warehouse_id",
            "Warehouse ID",
            "Warehouse or fulfillment center identifier.",
            aliases=("warehouse", "fulfillment center"),
        ),
    ),
    SOURCE_KIND_THREE_PL_INVOICE: (
        CanonicalFieldDefinition(
            "invoice_number",
            "Invoice Number",
            "3PL invoice number.",
            required=True,
            aliases=("invoice #", "invoice no"),
        ),
        CanonicalFieldDefinition(
            "invoice_date",
            "Invoice Date",
            "3PL invoice date.",
            required=True,
        ),
        CanonicalFieldDefinition(
            "warehouse_id",
            "Warehouse ID",
            "Warehouse or fulfillment center identifier.",
            aliases=("warehouse", "fulfillment center"),
        ),
        CanonicalFieldDefinition(
            "external_order_id",
            "External Order ID",
            "Order identifier referenced by the 3PL invoice.",
            aliases=("order id", "order identifier"),
        ),
        CanonicalFieldDefinition(
            "sku",
            "SKU",
            "Item or SKU identifier.",
            aliases=("item sku", "item"),
        ),
        CanonicalFieldDefinition(
            "charge_type",
            "Charge Type",
            "Type of 3PL charge.",
            required=True,
            aliases=("charge code", "fee type"),
        ),
        CanonicalFieldDefinition(
            "quantity",
            "Quantity",
            "Units billed for the charge.",
            aliases=("qty",),
        ),
        CanonicalFieldDefinition(
            "unit_rate",
            "Unit Rate",
            "Billed rate per unit.",
            aliases=("rate", "unit price"),
        ),
        CanonicalFieldDefinition(
            "amount",
            "Amount",
            "Total billed amount.",
            required=True,
            aliases=("charge amount", "invoice amount"),
        ),
        CanonicalFieldDefinition(
            "raw_row_ref",
            "Raw Row Reference",
            "Traceability reference for the original row.",
            aliases=("row ref", "row reference"),
        ),
    ),
    SOURCE_KIND_RATE_CARD: (
        CanonicalFieldDefinition(
            "provider_type",
            "Provider Type",
            "Provider category such as parcel or 3pl.",
            required=True,
            aliases=("provider", "type"),
        ),
        CanonicalFieldDefinition(
            "provider_name",
            "Provider Name",
            "Carrier or 3PL provider name.",
            required=True,
            aliases=("carrier", "vendor", "provider"),
        ),
        CanonicalFieldDefinition(
            "service_level",
            "Service Level",
            "Service level the rule applies to.",
            aliases=("service",),
        ),
        CanonicalFieldDefinition(
            "charge_type",
            "Charge Type",
            "Charge type covered by the rule.",
            required=True,
            aliases=("charge code", "fee type"),
        ),
        CanonicalFieldDefinition(
            "zone_min",
            "Zone Min",
            "Minimum zone covered by the rule.",
            aliases=("from zone", "zone start"),
        ),
        CanonicalFieldDefinition(
            "zone_max",
            "Zone Max",
            "Maximum zone covered by the rule.",
            aliases=("to zone", "zone end"),
        ),
        CanonicalFieldDefinition(
            "weight_min_lb",
            "Weight Min (lb)",
            "Minimum billed weight in pounds.",
            aliases=("min weight", "weight from"),
        ),
        CanonicalFieldDefinition(
            "weight_max_lb",
            "Weight Max (lb)",
            "Maximum billed weight in pounds.",
            aliases=("max weight", "weight to"),
        ),
        CanonicalFieldDefinition(
            "expected_rate",
            "Expected Rate",
            "Contracted rate for the rule.",
            required=True,
            aliases=("rate", "expected amount"),
        ),
        CanonicalFieldDefinition(
            "effective_start",
            "Effective Start",
            "Rule effective start date.",
            aliases=("start date",),
        ),
        CanonicalFieldDefinition(
            "effective_end",
            "Effective End",
            "Rule effective end date.",
            aliases=("end date",),
        ),
    ),
}


def _normalize_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.strip().lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> set[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return set()
    return set(normalized.split(" "))


def get_supported_source_kinds() -> tuple[str, ...]:
    return SOURCE_KIND_ORDERING


def get_canonical_fields(source_kind: str) -> tuple[CanonicalFieldDefinition, ...]:
    return CANONICAL_FIELD_REGISTRY.get(source_kind, ())


def is_valid_source_kind(source_kind: str) -> bool:
    return source_kind in CANONICAL_FIELD_REGISTRY


def infer_source_kind_from_filename(filename: str) -> Optional[str]:
    tokens = {
        token for token in re.split(r"[^a-z0-9]+", Path(filename).stem.lower()) if token
    }
    if not tokens:
        return None

    if "rate" in tokens and "card" in tokens:
        return SOURCE_KIND_RATE_CARD
    if "invoice" in tokens and (
        "3pl" in tokens
        or "threepl" in tokens
        or {"three", "pl"}.issubset(tokens)
        or "warehouse" in tokens
        or "fulfillment" in tokens
    ):
        return SOURCE_KIND_THREE_PL_INVOICE
    if "invoice" in tokens and ("parcel" in tokens or "carrier" in tokens):
        return SOURCE_KIND_PARCEL_INVOICE
    if "event" in tokens or "events" in tokens or "tracking" in tokens:
        return SOURCE_KIND_SHIPMENT_EVENT
    if "shipment" in tokens or "shipments" in tokens:
        return SOURCE_KIND_SHIPMENT
    if "order" in tokens or "orders" in tokens:
        return SOURCE_KIND_ORDER

    return None


def _field_aliases(field_definition: CanonicalFieldDefinition) -> set[str]:
    aliases = {
        _normalize_name(field_definition.name),
        _normalize_name(field_definition.label),
    }
    aliases.update(_normalize_name(alias) for alias in field_definition.aliases)
    return {alias for alias in aliases if alias}


def _score_column_for_field(
    column_name: str, field_definition: CanonicalFieldDefinition
) -> tuple[int, float, str]:
    normalized_column = _normalize_name(column_name)
    if not normalized_column:
        return (0, 0.0, "")

    aliases = _field_aliases(field_definition)
    if normalized_column in aliases:
        return (5, 0.99, "Exact header match.")

    column_tokens = _tokenize(column_name)
    best_partial_score = 0
    best_reason = ""
    for alias in aliases:
        alias_tokens = _tokenize(alias)
        if not alias_tokens:
            continue
        if alias_tokens == column_tokens:
            return (4, 0.95, "Normalized header match.")
        if alias_tokens.issubset(column_tokens):
            score = 3
            reason = "Header contains the canonical field tokens."
        elif column_tokens.issubset(alias_tokens):
            score = 2
            reason = "Header is a shorter variant of the canonical field."
        elif len(alias_tokens.intersection(column_tokens)) >= 2:
            score = 1
            reason = "Header shares key tokens with the canonical field."
        else:
            continue

        if score > best_partial_score:
            best_partial_score = score
            best_reason = reason

    if best_partial_score == 3:
        return (3, 0.8, best_reason)
    if best_partial_score == 2:
        return (2, 0.65, best_reason)
    if best_partial_score == 1:
        return (1, 0.55, best_reason)

    return (0, 0.0, "")


def infer_source_kind_from_columns(
    column_names: list[str],
    filename: str = "",
) -> Optional[str]:
    best_source_kind = infer_source_kind_from_filename(filename)
    best_score = 1 if best_source_kind else 0
    best_match_count = 0

    for source_kind in SOURCE_KIND_ORDERING:
        fields = get_canonical_fields(source_kind)
        score = 0
        matched_fields: set[str] = set()
        for column_name in column_names:
            column_best_score = 0
            column_best_field = ""
            for field_definition in fields:
                field_score, _, _ = _score_column_for_field(
                    column_name, field_definition
                )
                if field_score > column_best_score:
                    column_best_score = field_score
                    column_best_field = field_definition.name
            score += column_best_score
            if column_best_field:
                matched_fields.add(column_best_field)

        match_count = len(matched_fields)
        if score > best_score or (
            score == best_score and match_count > best_match_count
        ):
            best_source_kind = source_kind
            best_score = score
            best_match_count = match_count

    if best_score == 0:
        return None

    return best_source_kind


def suggest_column_mappings(
    column_names: list[str],
    source_kind: str,
) -> list[MappingSuggestion]:
    fields = get_canonical_fields(source_kind)
    if not fields:
        return []

    suggestions: list[MappingSuggestion] = []
    used_fields: set[str] = set()
    for column_name in column_names:
        best_field: Optional[CanonicalFieldDefinition] = None
        best_field_score = 0
        best_confidence = 0.0
        best_reason = ""
        for field_definition in fields:
            if field_definition.name in used_fields:
                continue
            field_score, confidence, reason = _score_column_for_field(
                column_name,
                field_definition,
            )
            if field_score > best_field_score:
                best_field = field_definition
                best_field_score = field_score
                best_confidence = confidence
                best_reason = reason

        if best_field is None or best_field_score < 3:
            continue

        used_fields.add(best_field.name)
        suggestions.append(
            MappingSuggestion(
                source_column=column_name,
                canonical_field=best_field.name,
                confidence=best_confidence,
                reason=best_reason,
            )
        )

    return suggestions
