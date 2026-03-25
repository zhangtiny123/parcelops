import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

from celery.signals import worker_ready

API_ROOT = Path(__file__).resolve().parents[1] / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.celery_app import broker_url, celery_app  # noqa: E402
import app.normalization_tasks  # noqa: F401, E402
from app.structured_logging import configure_logging, get_logger, log_event  # noqa: E402

configure_logging()
logger = get_logger(__name__)
app = celery_app


@app.task(name="parcelops.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@worker_ready.connect
def on_worker_ready(**_: object) -> None:
    broker = urlparse(broker_url)
    log_event(
        logger,
        logging.INFO,
        "worker.ready",
        broker_host=broker.hostname or "redis",
        broker_port=broker.port or 6379,
        broker_db=broker.path.lstrip("/") or "0",
    )
