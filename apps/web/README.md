# Web App

This is the Next.js frontend for ParcelOps Recovery Copilot.

## Current scope

Task 01 provides a minimal operator-facing placeholder page plus a simple `/health` endpoint for container health checks.

## Commands

Run inside the containerized stack from the repository root:

```bash
docker compose up --build web
```

Useful endpoints:

- App UI: `http://localhost:3000`
- Health: `http://localhost:3000/health`
