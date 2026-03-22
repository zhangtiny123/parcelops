# Task 01: Monorepo Bootstrap and Docker Compose Foundation

## Whole-picture context

ParcelOps Recovery Copilot is a local-first demo product with a Next.js frontend, FastAPI backend, Celery worker, Postgres, and Redis.

## Specific task goal

Create the initial repository structure and local runtime so the stack boots successfully, even if the first pages are placeholders.

## Requirements

- Create the top-level repo structure for `apps/web`, `apps/api`, `apps/worker`, `data`, `docs`, and `scripts`.
- Add `docker-compose.yml`.
- Add Dockerfiles for web, API, and worker.
- Add `.env.example`.
- Add a root `README.md` with local run instructions.
- Web should start and show a basic health page.
- API should start and expose `/health`.
- Worker should start and connect to Redis.
- Postgres and Redis should be reachable by Compose service name.

## Output

A bootable local development stack.

## Acceptance criteria

- `docker compose up --build` succeeds.
- `web` is reachable in a browser.
- `api` returns `200` on `/health`.
- `worker` boots without crashing.
- `README` explains how to run everything.
