from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from app.file_previews import FilePreview, load_file_preview
from app.models.uploads import UploadJob
from app.settings import get_settings


def get_storage_root() -> Path:
    return Path(get_settings().local_storage_root).resolve()


def resolve_upload_file_path(upload_job: UploadJob) -> Path:
    storage_root = get_storage_root()
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


def load_upload_preview(
    upload_job: UploadJob,
    row_limit: int | None = None,
) -> FilePreview:
    try:
        return load_file_preview(
            file_path=resolve_upload_file_path(upload_job),
            file_type=upload_job.file_type,
            row_limit=row_limit,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file could not be parsed for preview.",
        ) from exc
