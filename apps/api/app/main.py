from fastapi import FastAPI

from app.api.routes.meta import router as meta_router
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        summary="Backend foundation for ParcelOps Recovery Copilot",
    )
    app.include_router(meta_router)

    return app


app = create_app()
