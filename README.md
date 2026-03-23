# ParcelOps Recovery Copilot

ParcelOps Recovery Copilot is a local-first demo product for detecting parcel and 3PL billing errors, explaining what happened, and helping operators turn findings into recovery actions.

Task 01 is now implemented as a minimal bootstrap stack:

- `web`: Next.js placeholder operator dashboard at `http://localhost:3000`
- `api`: FastAPI service with `GET /health` at `http://localhost:8000/health`
- `worker`: Celery worker connected to Redis
- `postgres`: PostgreSQL for upcoming persistence work
- `redis`: Redis broker and cache

## Quick start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Build and start the stack:

   ```bash
   docker compose up --build
   ```

3. Check the running services:

   - Web UI: `http://localhost:3000`
   - Web health: `http://localhost:3000/health`
   - API health: `http://localhost:8000/health`
   - API DB health: `http://localhost:8000/db-health`
   - API docs: `http://localhost:8000/docs`

4. Stop the stack:

   ```bash
   docker compose down
   ```

To remove the database volume as well:

```bash
docker compose down -v
```

## Run Only Dependencies

If you want to run the API and worker directly on your machine while keeping only Postgres and Redis in Docker, use the dependency-only workflow.

1. Start just the backing services:

   ```bash
   ./scripts/start-deps.sh
   ```

2. Run the API locally from the repo root:

   ```bash
   ./scripts/run-api-local.sh
   ```

3. Run the worker locally from the repo root in a separate terminal:

   ```bash
   ./scripts/run-worker-local.sh
   ```

This workflow uses the host-exposed ports that Compose already publishes:

- Postgres: `localhost:5432`
- Redis: `localhost:6379`

The local run scripts automatically point `DATABASE_URL`, `CELERY_BROKER_URL`, and related settings at `localhost` unless you override them.

## Repository layout

```text
apps/
  api/            # FastAPI backend
  web/            # Next.js frontend
  worker/         # Celery worker
packages/
  shared/         # Shared contracts and types when needed
infra/
  postgres/       # Postgres-specific assets
  redis/          # Redis-specific assets
data/
  raw/            # Unmodified source files
  generated/      # Synthetic demo datasets
  uploads/        # Local mounted storage for demo uploads
docs/
  reference/      # Stable project reference
  tasks/          # One file per implementation task
scripts/          # Helper scripts and generators
docker-compose.yml
.env.example
```

## Service notes

- The stack is intentionally minimal and health-oriented for this bootstrap task.
- The web app is a placeholder operator shell, not the full product UI.
- Postgres is provisioned and reachable by service name, but schema setup begins in Task 02.
- The API applies Alembic migrations on startup before serving requests.
- The worker runs a basic Celery app and uses Redis as broker and result backend.
- Uploaded-file storage is mounted to `./data/uploads` for future ingestion work.

## Subsystem docs

- Web: [apps/web/README.md](apps/web/README.md)
- API: [apps/api/README.md](apps/api/README.md)
- Worker: [apps/worker/README.md](apps/worker/README.md)
- Reference docs: [docs/reference/README.md](docs/reference/README.md)
- Task index: [docs/tasks/README.md](docs/tasks/README.md)
