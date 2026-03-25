from time import perf_counter
import logging

from fastapi import FastAPI, Request

from app.api.routes.admin import router as admin_router
from app.api.routes.cases import router as cases_router
from app.api.routes.copilot import router as copilot_router
from app.api.routes.issues import router as issues_router
from app.api.routes.meta import router as meta_router
from app.api.routes.uploads import router as uploads_router
from app.celery_app import configure_celery_app
from app.models.common import generate_uuid
from app.settings import get_settings
from app.structured_logging import configure_logging, get_logger, log_event

logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    configure_celery_app()

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        summary="Backend foundation for ParcelOps Recovery Copilot",
    )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or generate_uuid()
        started_at = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = max(1, int((perf_counter() - started_at) * 1000))
            logger.exception(
                "http.request.failed",
                extra={
                    "event": "http.request.failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "latency_ms": latency_ms,
                },
            )
            raise

        response.headers["x-request-id"] = request_id
        log_event(
            logger,
            level=logging.INFO,
            event="http.request.completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=max(1, int((perf_counter() - started_at) * 1000)),
        )
        return response

    app.include_router(admin_router)
    app.include_router(meta_router)
    app.include_router(cases_router)
    app.include_router(copilot_router)
    app.include_router(issues_router)
    app.include_router(uploads_router)

    return app


app = create_app()
