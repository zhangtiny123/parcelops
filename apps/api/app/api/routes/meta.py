from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.health import get_database_health
from app.db.session import get_db
from app.settings import get_settings

router = APIRouter(tags=["meta"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/")
def read_root() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": "api",
        "name": settings.app_name,
        "docs_url": "/docs",
        "health_url": "/health",
        "db_health_url": "/db-health",
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
    }


@router.get("/db-health")
def read_db_health(db: DatabaseSession) -> dict[str, object]:
    try:
        return get_database_health(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity check failed.",
        ) from exc
