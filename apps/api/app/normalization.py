from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.billing import ParcelInvoiceLine, RateCardRule, ThreePLInvoiceLine
from app.models.common import utcnow
from app.models.observability import ENTITY_TYPE_UPLOAD_JOB
from app.models.fulfillment import OrderRecord, Shipment, ShipmentEvent
from app.models.uploads import (
    UPLOAD_STATUS_NORMALIZATION_FAILED,
    UPLOAD_STATUS_NORMALIZED,
    UPLOAD_STATUS_NORMALIZED_WITH_ERRORS,
    UPLOAD_STATUS_NORMALIZING,
    UploadJob,
    UploadMapping,
    UploadNormalizationError,
    UploadNormalizationRecord,
)
from app.observability import add_status_transition
from app.schema_mapping import (
    SOURCE_KIND_ORDER,
    SOURCE_KIND_PARCEL_INVOICE,
    SOURCE_KIND_RATE_CARD,
    SOURCE_KIND_SHIPMENT,
    SOURCE_KIND_SHIPMENT_EVENT,
    SOURCE_KIND_THREE_PL_INVOICE,
    get_canonical_fields,
    is_valid_source_kind,
)
from app.structured_logging import get_logger, log_event
from app.upload_files import load_upload_preview

LoaderResult = TypeVar(
    "LoaderResult",
    OrderRecord,
    Shipment,
    ShipmentEvent,
    ParcelInvoiceLine,
    ThreePLInvoiceLine,
    RateCardRule,
)
logger = get_logger(__name__)


class NormalizationConfigurationError(ValueError):
    pass


class RowNormalizationError(ValueError):
    pass


def normalize_upload(upload_job_id: str, db: Session) -> dict[str, int | str]:
    upload_job = db.get(UploadJob, upload_job_id)
    if upload_job is None:
        raise NormalizationConfigurationError("Upload job not found.")

    upload_mapping = db.scalar(
        select(UploadMapping).where(UploadMapping.upload_job_id == upload_job_id)
    )
    if upload_mapping is None:
        raise NormalizationConfigurationError(
            "Upload mapping is required before normalization."
        )

    _validate_mapping_is_normalizable(upload_mapping)

    previous_status = upload_job.status
    upload_job.status = UPLOAD_STATUS_NORMALIZING
    upload_job.normalization_started_at = utcnow()
    upload_job.normalization_completed_at = None
    upload_job.normalized_row_count = 0
    upload_job.normalization_error_count = 0
    upload_job.last_error = None
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_UPLOAD_JOB,
        entity_id=upload_job.id,
        status_from=previous_status,
        status_to=upload_job.status,
        summary="Upload normalization started.",
        metadata={
            "normalization_task_id": upload_job.normalization_task_id,
            "source_kind": upload_mapping.source_kind,
        },
    )
    db.commit()
    log_event(
        logger,
        logging.INFO,
        "upload.normalization.started",
        upload_id=upload_job.id,
        normalization_task_id=upload_job.normalization_task_id,
        source_kind=upload_mapping.source_kind,
        status=upload_job.status,
    )

    db.execute(
        delete(UploadNormalizationError).where(
            UploadNormalizationError.upload_job_id == upload_job_id
        )
    )
    db.execute(
        delete(UploadNormalizationRecord).where(
            UploadNormalizationRecord.upload_job_id == upload_job_id
        )
    )
    db.commit()

    normalized_row_count = 0
    normalization_error_count = 0
    try:
        file_preview = load_upload_preview(upload_job, row_limit=None)
        mapping_lookup = _build_mapping_lookup(upload_mapping)
        loader = _SOURCE_KIND_LOADERS[upload_mapping.source_kind]

        for row_number, raw_row in enumerate(file_preview.rows, start=2):
            mapped_row = _map_row(raw_row, mapping_lookup)
            raw_row_ref = _resolve_raw_row_ref(
                upload_job_id=upload_job.id,
                row_number=row_number,
                mapped_row=mapped_row,
            )

            try:
                canonical_record = loader(db, mapped_row, raw_row_ref)
                db.add(canonical_record)
                db.flush()
                db.add(
                    UploadNormalizationRecord(
                        upload_job_id=upload_job.id,
                        source_kind=upload_mapping.source_kind,
                        row_number=row_number,
                        raw_row_ref=raw_row_ref,
                        canonical_table=canonical_record.__tablename__,
                        canonical_record_id=canonical_record.id,
                    )
                )
                db.commit()
                normalized_row_count += 1
            except (RowNormalizationError, SQLAlchemyError) as exc:
                db.rollback()
                db.add(
                    UploadNormalizationError(
                        upload_job_id=upload_job.id,
                        source_kind=upload_mapping.source_kind,
                        row_number=row_number,
                        raw_row_ref=raw_row_ref,
                        error_message=str(exc),
                        row_data_json=dict(raw_row),
                    )
                )
                db.commit()
                normalization_error_count += 1
                log_event(
                    logger,
                    logging.WARNING,
                    "upload.normalization.row_error",
                    upload_id=upload_job.id,
                    source_kind=upload_mapping.source_kind,
                    row_number=row_number,
                    raw_row_ref=raw_row_ref,
                    error_message=str(exc),
                )
    except Exception as exc:
        db.rollback()
        upload_job = db.get(UploadJob, upload_job_id)
        if upload_job is not None:
            previous_status = upload_job.status
            upload_job.status = UPLOAD_STATUS_NORMALIZATION_FAILED
            upload_job.normalization_completed_at = utcnow()
            upload_job.normalized_row_count = normalized_row_count
            upload_job.normalization_error_count = normalization_error_count
            upload_job.last_error = _format_fatal_error(exc)
            add_status_transition(
                db,
                entity_type=ENTITY_TYPE_UPLOAD_JOB,
                entity_id=upload_job.id,
                status_from=previous_status,
                status_to=upload_job.status,
                summary="Upload normalization failed.",
                metadata={
                    "normalization_task_id": upload_job.normalization_task_id,
                    "normalized_row_count": normalized_row_count,
                    "normalization_error_count": normalization_error_count,
                    "last_error": upload_job.last_error,
                },
            )
            db.commit()
            logger.exception(
                "upload.normalization.failed",
                extra={
                    "event": "upload.normalization.failed",
                    "upload_id": upload_job.id,
                    "normalization_task_id": upload_job.normalization_task_id,
                    "normalized_row_count": normalized_row_count,
                    "normalization_error_count": normalization_error_count,
                },
            )
        raise

    upload_job = db.get(UploadJob, upload_job_id)
    if upload_job is None:
        raise NormalizationConfigurationError("Upload job disappeared mid-run.")

    previous_status = upload_job.status
    upload_job.status = (
        UPLOAD_STATUS_NORMALIZED_WITH_ERRORS
        if normalization_error_count > 0
        else UPLOAD_STATUS_NORMALIZED
    )
    upload_job.normalization_completed_at = utcnow()
    upload_job.normalized_row_count = normalized_row_count
    upload_job.normalization_error_count = normalization_error_count
    upload_job.last_error = None
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_UPLOAD_JOB,
        entity_id=upload_job.id,
        status_from=previous_status,
        status_to=upload_job.status,
        summary="Upload normalization completed.",
        metadata={
            "normalization_task_id": upload_job.normalization_task_id,
            "normalized_row_count": normalized_row_count,
            "normalization_error_count": normalization_error_count,
        },
    )
    db.commit()
    log_event(
        logger,
        logging.INFO,
        "upload.normalization.completed",
        upload_id=upload_job.id,
        normalization_task_id=upload_job.normalization_task_id,
        source_kind=upload_mapping.source_kind,
        status=upload_job.status,
        normalized_row_count=normalized_row_count,
        normalization_error_count=normalization_error_count,
    )

    return {
        "upload_job_id": upload_job_id,
        "status": upload_job.status,
        "normalized_row_count": normalized_row_count,
        "normalization_error_count": normalization_error_count,
    }


def _format_fatal_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc)


def _validate_mapping_is_normalizable(upload_mapping: UploadMapping) -> None:
    if not is_valid_source_kind(upload_mapping.source_kind):
        raise NormalizationConfigurationError(
            "Unsupported source kind for normalization."
        )

    mapped_fields = {
        mapping["canonical_field"] for mapping in upload_mapping.column_mappings_json
    }
    missing_fields = [
        field.name
        for field in get_canonical_fields(upload_mapping.source_kind)
        if field.required and field.name not in mapped_fields
    ]
    if missing_fields:
        raise NormalizationConfigurationError(
            "Missing required mappings for normalization: "
            + ", ".join(sorted(missing_fields))
        )


def _build_mapping_lookup(upload_mapping: UploadMapping) -> dict[str, str]:
    return {
        mapping["canonical_field"]: mapping["source_column"]
        for mapping in upload_mapping.column_mappings_json
    }


def _map_row(raw_row: dict[str, str], mapping_lookup: dict[str, str]) -> dict[str, str]:
    return {
        canonical_field: raw_row.get(source_column, "")
        for canonical_field, source_column in mapping_lookup.items()
    }


def _resolve_raw_row_ref(
    upload_job_id: str,
    row_number: int,
    mapped_row: dict[str, str],
) -> str:
    raw_row_ref = _optional_text(mapped_row.get("raw_row_ref"))
    if raw_row_ref is not None:
        return raw_row_ref
    return f"{upload_job_id}:row:{row_number}"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if normalized == "":
        return None
    return normalized


def _required_text(mapped_row: dict[str, str], field_name: str) -> str:
    value = _optional_text(mapped_row.get(field_name))
    if value is None:
        raise RowNormalizationError(f"Missing required value for {field_name}.")
    return value


def _parse_decimal(value: Any, field_name: str) -> Decimal | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise RowNormalizationError(
            f"Invalid decimal value for {field_name}: {normalized}"
        ) from exc


def _require_decimal(mapped_row: dict[str, str], field_name: str) -> Decimal:
    value = _parse_decimal(mapped_row.get(field_name), field_name)
    if value is None:
        raise RowNormalizationError(f"Missing required value for {field_name}.")
    return value


def _parse_int(value: Any, field_name: str) -> int | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError as exc:
        raise RowNormalizationError(
            f"Invalid integer value for {field_name}: {normalized}"
        ) from exc


def _parse_date(value: Any, field_name: str) -> date | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise RowNormalizationError(
            f"Invalid date value for {field_name}: {normalized}"
        ) from exc


def _require_date(mapped_row: dict[str, str], field_name: str) -> date:
    value = _parse_date(mapped_row.get(field_name), field_name)
    if value is None:
        raise RowNormalizationError(f"Missing required value for {field_name}.")
    return value


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None

    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError as exc:
            raise RowNormalizationError(
                f"Invalid datetime value for {field_name}: {normalized}"
            ) from exc
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_datetime(mapped_row: dict[str, str], field_name: str) -> datetime:
    value = _parse_datetime(mapped_row.get(field_name), field_name)
    if value is None:
        raise RowNormalizationError(f"Missing required value for {field_name}.")
    return value


def _lookup_order_id(db: Session, external_order_id: str | None) -> str | None:
    if external_order_id is None:
        return None
    return db.scalar(
        select(OrderRecord.id).where(OrderRecord.external_order_id == external_order_id)
    )


def _lookup_shipment_id(
    db: Session,
    external_shipment_id: str | None,
    tracking_number: str | None,
) -> str | None:
    if external_shipment_id is not None:
        shipment_id = db.scalar(
            select(Shipment.id).where(
                Shipment.external_shipment_id == external_shipment_id
            )
        )
        if shipment_id is not None:
            return shipment_id

    if tracking_number is None:
        return None

    return db.scalar(
        select(Shipment.id).where(Shipment.tracking_number == tracking_number)
    )


def _build_order_record(
    db: Session,
    mapped_row: dict[str, str],
    _: str,
) -> OrderRecord:
    return OrderRecord(
        external_order_id=_required_text(mapped_row, "external_order_id"),
        customer_ref=_optional_text(mapped_row.get("customer_ref")),
        order_date=_require_datetime(mapped_row, "order_date"),
        promised_service_level=_optional_text(mapped_row.get("promised_service_level")),
        warehouse_id=_optional_text(mapped_row.get("warehouse_id")),
    )


def _build_shipment(
    db: Session,
    mapped_row: dict[str, str],
    _: str,
) -> Shipment:
    external_order_id = _optional_text(mapped_row.get("external_order_id"))
    return Shipment(
        external_shipment_id=_required_text(mapped_row, "external_shipment_id"),
        order_id=_lookup_order_id(db, external_order_id),
        tracking_number=_required_text(mapped_row, "tracking_number"),
        carrier=_required_text(mapped_row, "carrier"),
        service_level=_optional_text(mapped_row.get("service_level")),
        origin_zip=_optional_text(mapped_row.get("origin_zip")),
        destination_zip=_optional_text(mapped_row.get("destination_zip")),
        zone=_optional_text(mapped_row.get("zone")),
        weight_lb=_parse_decimal(mapped_row.get("weight_lb"), "weight_lb"),
        dim_weight_lb=_parse_decimal(mapped_row.get("dim_weight_lb"), "dim_weight_lb"),
        shipped_at=_parse_datetime(mapped_row.get("shipped_at"), "shipped_at"),
        delivered_at=_parse_datetime(mapped_row.get("delivered_at"), "delivered_at"),
        warehouse_id=_optional_text(mapped_row.get("warehouse_id")),
    )


def _build_shipment_event(
    db: Session,
    mapped_row: dict[str, str],
    raw_row_ref: str,
) -> ShipmentEvent:
    return ShipmentEvent(
        tracking_number=_required_text(mapped_row, "tracking_number"),
        event_type=_required_text(mapped_row, "event_type"),
        event_time=_require_datetime(mapped_row, "event_time"),
        location=_optional_text(mapped_row.get("location")),
        raw_row_ref=raw_row_ref,
    )


def _build_parcel_invoice_line(
    db: Session,
    mapped_row: dict[str, str],
    raw_row_ref: str,
) -> ParcelInvoiceLine:
    external_shipment_id = _optional_text(mapped_row.get("external_shipment_id"))
    tracking_number = _required_text(mapped_row, "tracking_number")
    return ParcelInvoiceLine(
        invoice_number=_required_text(mapped_row, "invoice_number"),
        invoice_date=_require_date(mapped_row, "invoice_date"),
        tracking_number=tracking_number,
        carrier=_required_text(mapped_row, "carrier"),
        charge_type=_required_text(mapped_row, "charge_type"),
        service_level_billed=_optional_text(mapped_row.get("service_level_billed")),
        billed_weight_lb=_parse_decimal(
            mapped_row.get("billed_weight_lb"),
            "billed_weight_lb",
        ),
        zone_billed=_optional_text(mapped_row.get("zone_billed")),
        amount=_require_decimal(mapped_row, "amount"),
        currency=_optional_text(mapped_row.get("currency")) or "USD",
        shipment_id=_lookup_shipment_id(db, external_shipment_id, tracking_number),
        raw_row_ref=raw_row_ref,
    )


def _build_three_pl_invoice_line(
    db: Session,
    mapped_row: dict[str, str],
    raw_row_ref: str,
) -> ThreePLInvoiceLine:
    external_order_id = _optional_text(mapped_row.get("external_order_id"))
    return ThreePLInvoiceLine(
        invoice_number=_required_text(mapped_row, "invoice_number"),
        invoice_date=_require_date(mapped_row, "invoice_date"),
        warehouse_id=_optional_text(mapped_row.get("warehouse_id")),
        order_id=_lookup_order_id(db, external_order_id),
        sku=_optional_text(mapped_row.get("sku")),
        charge_type=_required_text(mapped_row, "charge_type"),
        quantity=_parse_int(mapped_row.get("quantity"), "quantity"),
        unit_rate=_parse_decimal(mapped_row.get("unit_rate"), "unit_rate"),
        amount=_require_decimal(mapped_row, "amount"),
        raw_row_ref=raw_row_ref,
    )


def _build_rate_card_rule(
    db: Session,
    mapped_row: dict[str, str],
    _: str,
) -> RateCardRule:
    provider_type = _required_text(mapped_row, "provider_type").lower()
    if provider_type not in {"parcel", "3pl"}:
        raise RowNormalizationError(
            f"Invalid provider_type value: {provider_type}. Expected parcel or 3pl."
        )

    return RateCardRule(
        provider_type=provider_type,
        provider_name=_required_text(mapped_row, "provider_name"),
        service_level=_optional_text(mapped_row.get("service_level")),
        charge_type=_required_text(mapped_row, "charge_type"),
        zone_min=_parse_int(mapped_row.get("zone_min"), "zone_min"),
        zone_max=_parse_int(mapped_row.get("zone_max"), "zone_max"),
        weight_min_lb=_parse_decimal(mapped_row.get("weight_min_lb"), "weight_min_lb"),
        weight_max_lb=_parse_decimal(mapped_row.get("weight_max_lb"), "weight_max_lb"),
        expected_rate=_require_decimal(mapped_row, "expected_rate"),
        effective_start=_parse_date(
            mapped_row.get("effective_start"), "effective_start"
        ),
        effective_end=_parse_date(mapped_row.get("effective_end"), "effective_end"),
    )


_SOURCE_KIND_LOADERS: dict[
    str, Callable[[Session, dict[str, str], str], LoaderResult]
] = {
    SOURCE_KIND_ORDER: _build_order_record,
    SOURCE_KIND_SHIPMENT: _build_shipment,
    SOURCE_KIND_SHIPMENT_EVENT: _build_shipment_event,
    SOURCE_KIND_PARCEL_INVOICE: _build_parcel_invoice_line,
    SOURCE_KIND_THREE_PL_INVOICE: _build_three_pl_invoice_line,
    SOURCE_KIND_RATE_CARD: _build_rate_card_rule,
}
