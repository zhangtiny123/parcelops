from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.health import get_database_health
from app.db.session import get_db
from app.settings import get_settings

router = APIRouter(tags=["meta"])


@router.get("/")
def read_root() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": "api",
        "name": settings.app_name,
        "docs_url": "/docs",
        "health_url": "/health",
        "db_health_url": "/db-health",
        "cases_url": "/cases",
        "copilot_chat_url": "/copilot/chat",
        "uploads_url": "/uploads",
        "issues_url": "/issues",
    }


@router.get("/health")
def read_health() -> dict[str, object]:
    settings = get_settings()
    return {
        "service": "api",
        "status": "ok",
        "environment": settings.app_env,
        "dependencies": {
            "postgres_host": settings.postgres_host,
            "postgres_db": settings.postgres_db,
            "redis_host": settings.redis_host,
        },
        "storage_root": settings.local_storage_root,
        "max_upload_size_bytes": settings.max_upload_size_bytes,
    }


@router.get("/db-health")
def read_db_health(db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    try:
        return get_database_health(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity check failed.",
        ) from exc
