from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_port: int
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
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_db=os.getenv("POSTGRES_DB", "parcelops"),
        redis_host=os.getenv("REDIS_HOST", "redis"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://parcelops:parcelops@postgres:5432/parcelops",
        ),
        local_storage_root=os.getenv("LOCAL_STORAGE_ROOT", "/data/uploads"),
    )
