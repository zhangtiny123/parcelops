from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.file_previews import FilePreview, load_file_preview
from app.models.common import generate_uuid
from app.models.uploads import UPLOAD_STATUS_UPLOADED, UploadJob, UploadMapping
from app.schema_mapping import (
    infer_source_kind_from_columns,
    infer_source_kind_from_filename,
    get_canonical_fields,
    get_supported_source_kinds,
    is_valid_source_kind,
    suggest_column_mappings,
)
from app.settings import get_settings

router = APIRouter(prefix="/uploads", tags=["uploads"])

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
    return Path(get_settings().local_storage_root).resolve()


def _get_upload_job_or_404(upload_id: str, db: Session) -> UploadJob:
    upload_job = db.get(UploadJob, upload_id)
    if upload_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload job not found.",
        )
    return upload_job


def _resolve_upload_file_path(upload_job: UploadJob) -> Path:
    storage_root = _get_storage_root()
    file_path = (storage_root / upload_job.storage_key).resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload storage path is invalid.",
        ) from exc

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file is no longer available.",
        )

    return file_path


def _load_upload_preview(upload_job: UploadJob) -> FilePreview:
    try:
        return load_file_preview(
            file_path=_resolve_upload_file_path(upload_job),
            file_type=upload_job.file_type,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file could not be parsed for preview.",
        ) from exc


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

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _cleanup_upload_path(destination_path, storage_root)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register upload metadata.",
        ) from exc

    db.refresh(upload_job)
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

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save upload mapping.",
        ) from exc

    db.refresh(upload_mapping)
    return _build_upload_mapping_read(upload_mapping)
