from fastapi import FastAPI

from app.settings import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Bootstrap API for ParcelOps Recovery Copilot",
)


@app.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    return {
        "service": "api",
        "name": settings.app_name,
        "docs_url": "/docs",
        "health_url": "/health",
    }


@app.get("/health", tags=["meta"])
def read_health() -> dict[str, object]:
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
