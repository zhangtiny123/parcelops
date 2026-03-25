from dataclasses import dataclass
from functools import lru_cache
import os


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_port: int
    copilot_provider: str
    database_echo: bool
    max_upload_size_bytes: int
    postgres_host: str
    postgres_db: str
    redis_host: str
    database_url: str
    local_storage_root: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name="ParcelOps Recovery Copilot API",
        app_env=os.getenv("APP_ENV", "development"),
        api_port=int(os.getenv("API_PORT", "8000")),
        copilot_provider=os.getenv("COPILOT_PROVIDER", "heuristic"),
        database_echo=os.getenv("DATABASE_ECHO", "0") == "1",
        max_upload_size_bytes=int(os.getenv("MAX_UPLOAD_SIZE_BYTES", "26214400")),
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_db=os.getenv("POSTGRES_DB", "parcelops"),
        redis_host=os.getenv("REDIS_HOST", "redis"),
        database_url=_normalize_database_url(
            os.getenv(
                "DATABASE_URL",
                "postgresql://parcelops:parcelops@postgres:5432/parcelops",
            ),
        ),
        local_storage_root=os.getenv("LOCAL_STORAGE_ROOT", "/data/uploads"),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
