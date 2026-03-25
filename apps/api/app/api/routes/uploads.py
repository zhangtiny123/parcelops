from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.file_previews import PREVIEW_ROW_LIMIT, FilePreview
from app.models.common import generate_uuid
from app.models.observability import ENTITY_TYPE_UPLOAD_JOB
from app.models.uploads import (
    UPLOAD_STATUS_MAPPED,
    UPLOAD_STATUS_NORMALIZATION_QUEUED,
    UPLOAD_STATUS_NORMALIZED,
    UPLOAD_STATUS_NORMALIZED_WITH_ERRORS,
    UPLOAD_STATUS_NORMALIZING,
    UPLOAD_STATUS_UPLOADED,
    UploadJob,
    UploadMapping,
    UploadNormalizationError,
    UploadNormalizationRecord,
)
from app.normalization_tasks import normalize_upload_task
from app.observability import add_status_transition
from app.schema_mapping import (
    infer_source_kind_from_columns,
    infer_source_kind_from_filename,
    get_canonical_fields,
    get_supported_source_kinds,
    is_valid_source_kind,
    suggest_column_mappings,
)
from app.settings import get_settings
from app.structured_logging import get_logger, log_event
from app.upload_files import get_storage_root, load_upload_preview

router = APIRouter(prefix="/uploads", tags=["uploads"])
logger = get_logger(__name__)

DEFAULT_UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_FILENAME_LENGTH = 255
SUPPORTED_UPLOAD_TYPES = {
    ".csv": {
        "file_type": "csv",
        "content_types": {
            "application/csv",
            "application/octet-stream",
            "application/vnd.ms-excel",
            "text/csv",
            "text/plain",
        },
    },
    ".xlsx": {
        "file_type": "xlsx",
        "content_types": {
            "application/octet-stream",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    },
}


class UploadJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: str
    source_kind: Optional[str]
    normalization_task_id: Optional[str]
    normalized_row_count: int
    normalization_error_count: int
    normalization_started_at: Optional[datetime]
    normalization_completed_at: Optional[datetime]
    last_error: Optional[str]
    uploaded_at: datetime


class CanonicalFieldRead(BaseModel):
    name: str
    label: str
    description: str
    required: bool


class ColumnMappingRead(BaseModel):
    source_column: str
    canonical_field: str


class ColumnMappingSuggestionRead(ColumnMappingRead):
    confidence: float
    reason: str


class UploadPreviewRead(BaseModel):
    upload_id: str
    columns: list[str]
    rows: list[dict[str, str]]
    preview_row_count: int
    inferred_source_kind: Optional[str]
    supported_source_kinds: list[str]


class UploadMappingWrite(BaseModel):
    source_column: str
    canonical_field: str


class UploadMappingUpsertRequest(BaseModel):
    source_kind: str
    mappings: list[UploadMappingWrite]


class UploadMappingRead(BaseModel):
    id: str
    upload_job_id: str
    source_kind: str
    mappings: list[ColumnMappingRead]
    created_at: datetime
    updated_at: datetime


class UploadSuggestedMappingRead(BaseModel):
    upload_id: str
    source_kind: Optional[str]
    inferred_source_kind: Optional[str]
    canonical_fields: list[CanonicalFieldRead]
    suggested_mappings: list[ColumnMappingSuggestionRead]
    saved_mapping: Optional[UploadMappingRead]


class UploadNormalizationErrorRead(BaseModel):
    id: str
    upload_job_id: str
    source_kind: str
    row_number: int
    raw_row_ref: Optional[str]
    error_message: str
    row_data: dict[str, str]
    created_at: datetime


class UploadNormalizationRecordRead(BaseModel):
    id: str
    upload_job_id: str
    source_kind: str
    row_number: int
    raw_row_ref: str
    canonical_table: str
    canonical_record_id: str
    created_at: datetime


def _sanitize_filename(filename: str | None) -> str:
    if filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must include a filename.",
        )

    safe_name = Path(filename).name.strip()
    if safe_name in {"", ".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must include a valid filename.",
        )

    if len(safe_name) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename exceeds the {MAX_FILENAME_LENGTH}-character limit.",
        )

    return safe_name


def _validate_file_type(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    upload_type = SUPPORTED_UPLOAD_TYPES.get(suffix)
    if upload_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only .csv and .xlsx uploads are supported.",
        )

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    allowed_content_types = upload_type["content_types"]
    if normalized_content_type and normalized_content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type for the supplied file extension.",
        )

    return str(upload_type["file_type"])


def _cleanup_upload_path(destination_path: Path, storage_root: Path) -> None:
    destination_path.unlink(missing_ok=True)

    if destination_path.parent == storage_root:
        return

    try:
        destination_path.parent.rmdir()
    except OSError:
        pass


async def _persist_file(
    uploaded_file: UploadFile,
    destination_path: Path,
    storage_root: Path,
    max_upload_size_bytes: int,
) -> int:
    total_bytes = 0
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with destination_path.open("wb") as handle:
            while chunk := await uploaded_file.read(DEFAULT_UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > max_upload_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Uploaded file exceeds the "
                            f"{max_upload_size_bytes}-byte limit."
                        ),
                    )
                handle.write(chunk)
    except HTTPException:
        _cleanup_upload_path(destination_path, storage_root)
        raise
    except OSError as exc:
        _cleanup_upload_path(destination_path, storage_root)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist uploaded file.",
        ) from exc
    finally:
        await uploaded_file.close()

    if total_bytes == 0:
        _cleanup_upload_path(destination_path, storage_root)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    return total_bytes


def _get_storage_root() -> Path:
    return get_storage_root()


def _get_upload_job_or_404(upload_id: str, db: Session) -> UploadJob:
    upload_job = db.get(UploadJob, upload_id)
    if upload_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload job not found.",
        )
    return upload_job


def _load_upload_preview(upload_job: UploadJob) -> FilePreview:
    return load_upload_preview(upload_job, row_limit=PREVIEW_ROW_LIMIT)


def _get_upload_mapping(upload_job_id: str, db: Session) -> Optional[UploadMapping]:
    statement = select(UploadMapping).where(
        UploadMapping.upload_job_id == upload_job_id
    )
    return db.scalar(statement)


def _build_canonical_field_reads(
    source_kind: Optional[str],
) -> list[CanonicalFieldRead]:
    if source_kind is None:
        return []

    return [
        CanonicalFieldRead(
            name=field_definition.name,
            label=field_definition.label,
            description=field_definition.description,
            required=field_definition.required,
        )
        for field_definition in get_canonical_fields(source_kind)
    ]


def _build_upload_mapping_read(upload_mapping: UploadMapping) -> UploadMappingRead:
    return UploadMappingRead(
        id=upload_mapping.id,
        upload_job_id=upload_mapping.upload_job_id,
        source_kind=upload_mapping.source_kind,
        mappings=[
            ColumnMappingRead(**column_mapping)
            for column_mapping in upload_mapping.column_mappings_json
        ],
        created_at=upload_mapping.created_at,
        updated_at=upload_mapping.updated_at,
    )


def _validate_mapping_request(
    request: UploadMappingUpsertRequest,
    preview: FilePreview,
) -> None:
    if not is_valid_source_kind(request.source_kind):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported source kind for mapping.",
        )

    preview_columns = set(preview.columns)
    valid_canonical_fields = {
        field_definition.name
        for field_definition in get_canonical_fields(request.source_kind)
    }

    source_columns = [mapping.source_column for mapping in request.mappings]
    if len(source_columns) != len(set(source_columns)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each source column can only be mapped once.",
        )

    canonical_fields = [mapping.canonical_field for mapping in request.mappings]
    if len(canonical_fields) != len(set(canonical_fields)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each canonical field can only be mapped once.",
        )

    for mapping in request.mappings:
        if mapping.source_column not in preview_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown source column: {mapping.source_column}",
            )
        if mapping.canonical_field not in valid_canonical_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown canonical field: {mapping.canonical_field}",
            )


def _missing_required_mapping_fields(
    source_kind: str,
    mappings: list[dict[str, str]],
) -> list[str]:
    mapped_fields = {mapping["canonical_field"] for mapping in mappings}
    return [
        field.name
        for field in get_canonical_fields(source_kind)
        if field.required and field.name not in mapped_fields
    ]


def _upload_has_normalization_records(upload_job_id: str, db: Session) -> bool:
    statement = (
        select(UploadNormalizationRecord.id)
        .where(UploadNormalizationRecord.upload_job_id == upload_job_id)
        .limit(1)
    )
    return db.scalar(statement) is not None


def _mapping_updates_locked(upload_job: UploadJob) -> bool:
    return upload_job.status in {
        UPLOAD_STATUS_NORMALIZATION_QUEUED,
        UPLOAD_STATUS_NORMALIZING,
        UPLOAD_STATUS_NORMALIZED,
        UPLOAD_STATUS_NORMALIZED_WITH_ERRORS,
    }


@router.post("", response_model=UploadJobRead, status_code=status.HTTP_201_CREATED)
async def create_upload(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
) -> UploadJob:
    settings = get_settings()
    storage_root = Path(settings.local_storage_root).resolve()

    original_filename = _sanitize_filename(file.filename)
    file_type = _validate_file_type(original_filename, file.content_type)
    upload_id = generate_uuid()
    storage_key = f"{upload_id}/{original_filename}"
    destination_path = storage_root / storage_key

    file_size_bytes = await _persist_file(
        uploaded_file=file,
        destination_path=destination_path,
        storage_root=storage_root,
        max_upload_size_bytes=settings.max_upload_size_bytes,
    )

    upload_job = UploadJob(
        id=upload_id,
        original_filename=original_filename,
        storage_key=storage_key,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        status=UPLOAD_STATUS_UPLOADED,
        source_kind=infer_source_kind_from_filename(original_filename),
    )
    db.add(upload_job)
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_UPLOAD_JOB,
        entity_id=upload_job.id,
        status_from=None,
        status_to=upload_job.status,
        summary="Upload received.",
        metadata={
            "original_filename": upload_job.original_filename,
            "file_type": upload_job.file_type,
            "file_size_bytes": upload_job.file_size_bytes,
            "source_kind": upload_job.source_kind,
        },
    )

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _cleanup_upload_path(destination_path, storage_root)
        logger.exception(
            "upload.create.failed",
            extra={
                "event": "upload.create.failed",
                "upload_id": upload_id,
                "original_filename": original_filename,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register upload metadata.",
        ) from exc

    db.refresh(upload_job)
    log_event(
        logger,
        logging.INFO,
        "upload.created",
        upload_id=upload_job.id,
        original_filename=upload_job.original_filename,
        file_type=upload_job.file_type,
        file_size_bytes=upload_job.file_size_bytes,
        source_kind=upload_job.source_kind,
        status=upload_job.status,
    )
    return upload_job


@router.get("", response_model=list[UploadJobRead])
def list_uploads(db: Annotated[Session, Depends(get_db)]) -> list[UploadJob]:
    statement = select(UploadJob).order_by(UploadJob.uploaded_at.desc())
    return list(db.scalars(statement))


@router.get("/{upload_id}", response_model=UploadJobRead)
def get_upload(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> UploadJob:
    return _get_upload_job_or_404(upload_id, db)


@router.get("/{upload_id}/preview", response_model=UploadPreviewRead)
def get_upload_preview(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> UploadPreviewRead:
    upload_job = _get_upload_job_or_404(upload_id, db)
    preview = _load_upload_preview(upload_job)
    inferred_source_kind = infer_source_kind_from_columns(
        column_names=preview.columns,
        filename=upload_job.original_filename,
    )
    return UploadPreviewRead(
        upload_id=upload_job.id,
        columns=preview.columns,
        rows=preview.rows,
        preview_row_count=len(preview.rows),
        inferred_source_kind=inferred_source_kind,
        supported_source_kinds=list(get_supported_source_kinds()),
    )


@router.get("/{upload_id}/suggested-mapping", response_model=UploadSuggestedMappingRead)
def get_upload_suggested_mapping(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
    source_kind: Optional[str] = None,
) -> UploadSuggestedMappingRead:
    upload_job = _get_upload_job_or_404(upload_id, db)
    preview = _load_upload_preview(upload_job)
    inferred_source_kind = infer_source_kind_from_columns(
        column_names=preview.columns,
        filename=upload_job.original_filename,
    )
    selected_source_kind = source_kind or inferred_source_kind or upload_job.source_kind
    if selected_source_kind is not None and not is_valid_source_kind(
        selected_source_kind
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported source kind for mapping suggestions.",
        )

    saved_mapping = _get_upload_mapping(upload_job.id, db)
    suggested_mappings = []
    if selected_source_kind is not None:
        suggested_mappings = [
            ColumnMappingSuggestionRead(
                source_column=suggestion.source_column,
                canonical_field=suggestion.canonical_field,
                confidence=suggestion.confidence,
                reason=suggestion.reason,
            )
            for suggestion in suggest_column_mappings(
                preview.columns, selected_source_kind
            )
        ]

    return UploadSuggestedMappingRead(
        upload_id=upload_job.id,
        source_kind=selected_source_kind,
        inferred_source_kind=inferred_source_kind,
        canonical_fields=_build_canonical_field_reads(selected_source_kind),
        suggested_mappings=suggested_mappings,
        saved_mapping=(
            _build_upload_mapping_read(saved_mapping)
            if saved_mapping is not None
            else None
        ),
    )


@router.get("/{upload_id}/mapping", response_model=UploadMappingRead)
def get_upload_mapping(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> UploadMappingRead:
    _get_upload_job_or_404(upload_id, db)
    upload_mapping = _get_upload_mapping(upload_id, db)
    if upload_mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload mapping not found.",
        )

    return _build_upload_mapping_read(upload_mapping)


@router.put("/{upload_id}/mapping", response_model=UploadMappingRead)
def save_upload_mapping(
    upload_id: str,
    request: UploadMappingUpsertRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UploadMappingRead:
    upload_job = _get_upload_job_or_404(upload_id, db)
    previous_status = upload_job.status
    if _mapping_updates_locked(upload_job):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload mapping cannot be changed after normalization has started.",
        )
    preview = _load_upload_preview(upload_job)
    _validate_mapping_request(request, preview)

    upload_mapping = _get_upload_mapping(upload_job.id, db)
    mapping_payload = [
        {
            "source_column": mapping.source_column,
            "canonical_field": mapping.canonical_field,
        }
        for mapping in request.mappings
    ]
    if upload_mapping is None:
        upload_mapping = UploadMapping(
            upload_job_id=upload_job.id,
            source_kind=request.source_kind,
            column_mappings_json=mapping_payload,
        )
        db.add(upload_mapping)
    else:
        upload_mapping.source_kind = request.source_kind
        upload_mapping.column_mappings_json = mapping_payload

    upload_job.source_kind = request.source_kind
    upload_job.status = UPLOAD_STATUS_MAPPED
    upload_job.normalization_task_id = None
    upload_job.normalized_row_count = 0
    upload_job.normalization_error_count = 0
    upload_job.normalization_started_at = None
    upload_job.normalization_completed_at = None
    upload_job.last_error = None
    if previous_status != upload_job.status:
        add_status_transition(
            db,
            entity_type=ENTITY_TYPE_UPLOAD_JOB,
            entity_id=upload_job.id,
            status_from=previous_status,
            status_to=upload_job.status,
            summary="Upload mapping saved.",
            metadata={
                "source_kind": request.source_kind,
                "mapping_count": len(mapping_payload),
            },
        )

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "upload.mapping_save.failed",
            extra={
                "event": "upload.mapping_save.failed",
                "upload_id": upload_job.id,
                "source_kind": request.source_kind,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save upload mapping.",
        ) from exc

    db.refresh(upload_mapping)
    log_event(
        logger,
        logging.INFO,
        "upload.mapping_saved",
        upload_id=upload_job.id,
        source_kind=request.source_kind,
        mapping_count=len(mapping_payload),
        status=upload_job.status,
    )
    return _build_upload_mapping_read(upload_mapping)


@router.post("/{upload_id}/normalize", response_model=UploadJobRead)
def trigger_upload_normalization(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> UploadJob:
    upload_job = _get_upload_job_or_404(upload_id, db)
    previous_status = upload_job.status
    if upload_job.status in {
        UPLOAD_STATUS_NORMALIZATION_QUEUED,
        UPLOAD_STATUS_NORMALIZING,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Normalization is already in progress for this upload.",
        )

    if upload_job.status in {
        UPLOAD_STATUS_NORMALIZED,
        UPLOAD_STATUS_NORMALIZED_WITH_ERRORS,
    } or _upload_has_normalization_records(upload_job.id, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload has already been normalized. Create a new upload to rerun it.",
        )

    upload_mapping = _get_upload_mapping(upload_job.id, db)
    if upload_mapping is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload mapping is required before normalization.",
        )

    missing_fields = _missing_required_mapping_fields(
        upload_mapping.source_kind,
        upload_mapping.column_mappings_json,
    )
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Missing required mappings for normalization: "
                + ", ".join(sorted(missing_fields))
            ),
        )

    task_id = generate_uuid()
    upload_job.status = UPLOAD_STATUS_NORMALIZATION_QUEUED
    upload_job.normalization_task_id = task_id
    upload_job.normalized_row_count = 0
    upload_job.normalization_error_count = 0
    upload_job.normalization_started_at = None
    upload_job.normalization_completed_at = None
    upload_job.last_error = None
    add_status_transition(
        db,
        entity_type=ENTITY_TYPE_UPLOAD_JOB,
        entity_id=upload_job.id,
        status_from=previous_status,
        status_to=upload_job.status,
        summary="Upload normalization queued.",
        metadata={
            "normalization_task_id": task_id,
            "source_kind": upload_job.source_kind,
        },
    )

    try:
        db.commit()
        normalize_upload_task.apply_async(args=[upload_job.id], task_id=task_id)
    except Exception as exc:
        db.rollback()
        upload_job = _get_upload_job_or_404(upload_id, db)
        dispatch_previous_status = upload_job.status
        upload_job.status = UPLOAD_STATUS_MAPPED
        upload_job.normalization_task_id = None
        upload_job.last_error = "Failed to dispatch normalization task."
        add_status_transition(
            db,
            entity_type=ENTITY_TYPE_UPLOAD_JOB,
            entity_id=upload_job.id,
            status_from=dispatch_previous_status,
            status_to=upload_job.status,
            summary="Upload normalization dispatch failed.",
            metadata={"last_error": upload_job.last_error},
        )
        db.commit()
        logger.exception(
            "upload.normalization_dispatch.failed",
            extra={
                "event": "upload.normalization_dispatch.failed",
                "upload_id": upload_job.id,
                "normalization_task_id": task_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch normalization task.",
        ) from exc

    db.expire_all()
    log_event(
        logger,
        logging.INFO,
        "upload.normalization.queued",
        upload_id=upload_job.id,
        normalization_task_id=task_id,
        source_kind=upload_job.source_kind,
        status=upload_job.status,
    )
    return _get_upload_job_or_404(upload_id, db)


@router.get(
    "/{upload_id}/normalization-errors",
    response_model=list[UploadNormalizationErrorRead],
)
def list_upload_normalization_errors(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[UploadNormalizationErrorRead]:
    _get_upload_job_or_404(upload_id, db)
    statement = (
        select(UploadNormalizationError)
        .where(UploadNormalizationError.upload_job_id == upload_id)
        .order_by(
            UploadNormalizationError.row_number.asc(),
            UploadNormalizationError.created_at.asc(),
        )
    )
    return [
        UploadNormalizationErrorRead(
            id=error.id,
            upload_job_id=error.upload_job_id,
            source_kind=error.source_kind,
            row_number=error.row_number,
            raw_row_ref=error.raw_row_ref,
            error_message=error.error_message,
            row_data={key: str(value) for key, value in error.row_data_json.items()},
            created_at=error.created_at,
        )
        for error in db.scalars(statement)
    ]


@router.get(
    "/{upload_id}/normalization-records",
    response_model=list[UploadNormalizationRecordRead],
)
def list_upload_normalization_records(
    upload_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[UploadNormalizationRecordRead]:
    _get_upload_job_or_404(upload_id, db)
    statement = (
        select(UploadNormalizationRecord)
        .where(UploadNormalizationRecord.upload_job_id == upload_id)
        .order_by(
            UploadNormalizationRecord.row_number.asc(),
            UploadNormalizationRecord.created_at.asc(),
        )
    )
    return [
        UploadNormalizationRecordRead(
            id=record.id,
            upload_job_id=record.upload_job_id,
            source_kind=record.source_kind,
            row_number=record.row_number,
            raw_row_ref=record.raw_row_ref,
            canonical_table=record.canonical_table,
            canonical_record_id=record.canonical_record_id,
            created_at=record.created_at,
        )
        for record in db.scalars(statement)
    ]
