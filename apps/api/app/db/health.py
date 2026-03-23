from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.settings import get_settings


def get_database_health(session: Session) -> dict[str, Any]:
    session.execute(text("SELECT 1")).scalar_one()

    engine = session.get_bind()
    if engine is None:
        raise RuntimeError("Database engine is not available.")

    inspector = inspect(engine)
    database_url = make_url(get_settings().database_url)

    return {
        "service": "database",
        "status": "ok",
        "database": {
            "driver": database_url.drivername,
            "name": database_url.database,
            "host": database_url.host,
        },
        "tables": sorted(inspector.get_table_names()),
    }
