# API Service

This is the FastAPI backend for ParcelOps Recovery Copilot.

## Current scope

Task 01 provides:

- the FastAPI application entrypoint
- environment-driven service settings
- `GET /health`
- generated docs at `/docs`

Database schema and persistence work start in Task 02.

## Commands

Run inside the containerized stack from the repository root:

```bash
docker compose up --build api
```

Useful endpoints:

- Health: `http://localhost:8000/health`
- Docs: `http://localhost:8000/docs`
