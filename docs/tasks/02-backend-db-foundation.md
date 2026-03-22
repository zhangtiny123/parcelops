# Task 02: Backend Application Skeleton and Database Foundation

## Whole-picture context

The backend is the orchestration layer for uploads, normalization, issue detection, copilot tools, and recovery case workflows.

## Specific task goal

Set up the FastAPI project structure, SQLAlchemy and Alembic foundation, and the initial database schema for the core entities.

## Requirements

- Create the FastAPI app with a clear module structure.
- Add SQLAlchemy models or an equivalent ORM.
- Add Alembic migrations.
- Implement models for Shipment, ParcelInvoiceLine, ShipmentEvent, OrderRecord, ThreePLInvoiceLine, RateCardRule, RecoveryIssue, and RecoveryCase.
- Add `/health` and `/db-health`.
- Add environment-based database config.
- Add the initial migration.

## Output

Backend foundation with schema bootstrapped in Postgres.

## Acceptance criteria

- Database tables are created through migrations.
- `/db-health` confirms connectivity.
- Models are separated cleanly by domain.
- A developer can inspect the schema by running the app locally.
