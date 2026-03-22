# Repo Structure

Codex should aim for the following repository layout:

```text
parcelops-recovery-copilot/
  apps/
    web/                 # Next.js frontend
    api/                 # FastAPI backend
    worker/              # Celery worker entrypoint
  packages/
    shared/              # Shared types/contracts if useful
  infra/
    postgres/
    redis/
  data/
    raw/
    generated/
    uploads/
  docs/
  scripts/
  docker-compose.yml
  .env.example
  README.md
```

This exact structure can be adjusted when implementation begins, but the final shape should stay simple and understandable.
