from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

LOGGER_NAMESPACE = "parcelops"
_LOGGER_ATTRIBUTE = "_parcelops_structured_logging"
_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", record.getMessage()),
        }
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_FIELDS
            and key not in {"asctime", "event", "message"}
        }
        if context:
            payload["context"] = context
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=True)


def configure_logging() -> None:
    logger = logging.getLogger(LOGGER_NAMESPACE)
    if getattr(logger, _LOGGER_ATTRIBUTE, False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    setattr(logger, _LOGGER_ATTRIBUTE, True)


def get_logger(name: str | None = None) -> logging.Logger:
    if name is None or name == "":
        return logging.getLogger(LOGGER_NAMESPACE)
    if name.startswith(f"{LOGGER_NAMESPACE}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **context: object,
) -> None:
    logger.log(level, event, extra={"event": event, **context})
