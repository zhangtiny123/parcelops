from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.db.session import reset_database_state
from app.main import create_app
from app.settings import reset_settings_cache
from conftest import run_migrations

EXPECTED_TABLES = {
    "order_records",
    "parcel_invoice_lines",
    "rate_card_rules",
    "recovery_cases",
    "recovery_issues",
    "shipment_events",
    "shipments",
    "upload_mappings",
    "upload_normalization_errors",
    "upload_normalization_records",
    "three_pl_invoice_lines",
    "upload_jobs",
}


def test_initial_migration_creates_expected_tables(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'parcelops.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_settings_cache()
    reset_database_state()

    run_migrations(database_url)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
    finally:
        engine.dispose()


def test_db_health_reports_connectivity(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'parcelops-health.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_settings_cache()
    reset_database_state()

    run_migrations(database_url)
    reset_settings_cache()
    reset_database_state()

    with TestClient(create_app()) as client:
        response = client.get("/db-health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["driver"] == "sqlite"
    assert EXPECTED_TABLES.issubset(set(payload["tables"]))
