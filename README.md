# ParcelOps Recovery Copilot

ParcelOps Recovery Copilot is a local-first demo product for detecting parcel and 3PL billing errors, explaining why they happened, and helping operators generate recovery actions.

This repository is scaffolded for stepwise implementation. The original all-in-one starter document has been split into focused reference docs and one task file per implementation step so future work can stay scoped and easy to navigate.

## Repository layout

```text
apps/
  api/            # FastAPI backend
  web/            # Next.js frontend
  worker/         # Celery worker
packages/
  shared/         # Shared contracts/types when needed
infra/
  postgres/       # Postgres-specific assets
  redis/          # Redis-specific assets
data/
  raw/            # Unmodified source files
  generated/      # Synthetic demo datasets
  uploads/        # Local uploaded files for the demo
docs/
  reference/      # Stable product and architecture reference
  tasks/          # One file per implementation task
scripts/          # Helper scripts and generators
```

## Documentation map

- Reference index: [docs/reference/README.md](docs/reference/README.md)
- Task index: [docs/tasks/README.md](docs/tasks/README.md)
- First implementation task: [docs/tasks/01-bootstrap-compose.md](docs/tasks/01-bootstrap-compose.md)

## Current state

The repo now contains:

- the initial directory scaffold for the planned monorepo
- stable reference docs for product context and constraints
- one task file per implementation step from bootstrap through demo polish

Application code, Compose services, and runtime setup should start with Task 01.
