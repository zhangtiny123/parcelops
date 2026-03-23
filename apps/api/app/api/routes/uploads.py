from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing_extensions import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.common import generate_uuid
from app.models.uploads import UPLOAD_STATUS_UPLOADED, UploadJob
from app.settings import get_settings

router = APIRouter(prefix="/uploads", tags=["uploads"])
DatabaseSession = Annotated[Session, Depends(get_db)]
IncomingUploadFile = Annotated[UploadFile, File(...)]

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


def _infer_source_kind(filename: str) -> str | None:
    tokens = {
        token for token in re.split(r"[^a-z0-9]+", Path(filename).stem.lower()) if token
    }
    if not tokens:
        return None

    if "rate" in tokens and "card" in tokens:
        return "rate_card"
    if "invoice" in tokens and (
        "3pl" in tokens
        or "threepl" in tokens
        or {"three", "pl"}.issubset(tokens)
        or "warehouse" in tokens
        or "fulfillment" in tokens
    ):
        return "three_pl_invoice"
    if "invoice" in tokens and ("parcel" in tokens or "carrier" in tokens):
        return "parcel_invoice"
    if "event" in tokens or "events" in tokens or "tracking" in tokens:
        return "shipment_event"
    if "shipment" in tokens or "shipments" in tokens:
        return "shipment"
    if "order" in tokens or "orders" in tokens:
        return "order"

    return None


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


@router.post("", response_model=UploadJobRead, status_code=status.HTTP_201_CREATED)
async def create_upload(
    file: IncomingUploadFile,
    db: DatabaseSession,
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
        source_kind=_infer_source_kind(original_filename),
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
def list_uploads(db: DatabaseSession) -> list[UploadJob]:
    statement = select(UploadJob).order_by(UploadJob.uploaded_at.desc())
    return list(db.scalars(statement))


@router.get("/{upload_id}", response_model=UploadJobRead)
def get_upload(upload_id: str, db: DatabaseSession) -> UploadJob:
    upload_job = db.get(UploadJob, upload_id)
    if upload_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload job not found.",
        )

    return upload_job
