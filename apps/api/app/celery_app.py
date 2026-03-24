from __future__ import annotations

import os

from celery import Celery


def _redis_url(database_index: str) -> str:
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{redis_host}:{redis_port}/{database_index}"


def _broker_url() -> str:
    return os.getenv(
        "CELERY_BROKER_URL",
        _redis_url(os.getenv("REDIS_BROKER_DB", "0")),
    )


def _result_backend() -> str:
    return os.getenv(
        "CELERY_RESULT_BACKEND",
        _redis_url(os.getenv("REDIS_RESULT_DB", "1")),
    )


celery_app = Celery("parcelops_worker")
broker_url = ""
result_backend = ""


def configure_celery_app() -> None:
    global broker_url, result_backend

    broker_url = _broker_url()
    result_backend = _result_backend()
    celery_app.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
        broker_connection_retry_on_startup=True,
        task_default_queue="parcelops",
        task_track_started=True,
        task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1"
        or os.getenv("APP_ENV") == "test",
        task_eager_propagates=False,
    )


configure_celery_app()
