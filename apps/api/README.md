# API Service

This is the FastAPI backend for ParcelOps Recovery Copilot.

## Current scope

Task 02 provides:

- the FastAPI application entrypoint and route structure
- environment-driven service and database settings
- SQLAlchemy models split by domain
- Alembic migrations with an initial schema
- `GET /health`
- `GET /db-health`
- generated docs at `/docs`

Task 07 adds:

- `POST /issues/detect` to run deterministic recovery-issue detection against canonical data
- `GET /issues` to list detected recovery issues with basic filters

## Commands

Run the API service inside the containerized stack from the repository root:

```bash
docker compose up --build api
```

Run only the backing services in Docker and the API on the host:

```bash
../../scripts/start-deps.sh
../../scripts/run-api-local.sh
```

Run migrations locally from `apps/api`:

```bash
./.venv/bin/alembic upgrade head
```

Useful endpoints after the database is available:

- Health: `http://localhost:8000/health`
- DB health: `http://localhost:8000/db-health`
- Issues: `http://localhost:8000/issues`
- Docs: `http://localhost:8000/docs`
