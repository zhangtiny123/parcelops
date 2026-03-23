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
