from __future__ import annotations

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.normalization import normalize_upload


@celery_app.task(name="parcelops.normalize_upload")
def normalize_upload_task(upload_job_id: str) -> dict[str, int | str]:
    session_factory = get_session_factory()
    with session_factory() as db:
        return normalize_upload(upload_job_id, db)
