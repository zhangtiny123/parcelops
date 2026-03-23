import logging
import os
from urllib.parse import urlparse

from celery import Celery
from celery.signals import worker_ready


def _redis_url(database_index: str) -> str:
    redis_host = os.getenv("REDIS_HOST", "redis")
    return f"redis://{redis_host}:6379/{database_index}"


broker_url = os.getenv(
    "CELERY_BROKER_URL",
    _redis_url(os.getenv("REDIS_BROKER_DB", "0")),
)
result_backend = os.getenv(
    "CELERY_RESULT_BACKEND",
    _redis_url(os.getenv("REDIS_RESULT_DB", "1")),
)

app = Celery("parcelops_worker", broker=broker_url, backend=result_backend)
app.conf.update(
    broker_connection_retry_on_startup=True,
    task_default_queue="parcelops",
    task_track_started=True,
)

logger = logging.getLogger(__name__)


@app.task(name="parcelops.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@worker_ready.connect
def on_worker_ready(**_: object) -> None:
    broker = urlparse(broker_url)
    logger.info(
        "Worker connected to Redis broker at %s:%s db=%s",
        broker.hostname or "redis",
        broker.port or 6379,
        broker.path.lstrip("/") or "0",
    )
