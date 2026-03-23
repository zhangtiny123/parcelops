# Worker Service

This is the Celery worker for ParcelOps Recovery Copilot.

## Current scope

Task 01 provides:

- a Celery worker process
- Redis-backed broker and result backend configuration
- a basic `parcelops.ping` task
- startup logging that confirms the Redis host target

Job orchestration and normalization work start in later tasks.

## Commands

Run inside the containerized stack from the repository root:

```bash
docker compose up --build worker
```

Run only the backing services in Docker and the worker on the host:

```bash
../../scripts/start-deps.sh
../../scripts/run-worker-local.sh
```
