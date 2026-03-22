# Implementation Constraints

Codex should follow these constraints for all tasks.

## Local-first deployment

1. Deployment must be local-first using Docker Compose only.
2. Do not use Kubernetes.
3. Do not assume Vercel, Render, Supabase, or other hosted services.
4. The full app must run with `docker compose up`.

## Tech stack

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Python
- Database: PostgreSQL
- Analytics and data processing: DuckDB and or Polars
- Background jobs: Celery
- Cache and broker: Redis
- Object and file storage for demo: local mounted volume
- AI layer: provider-agnostic wrapper with tool-calling support
- Observability: OpenTelemetry-compatible structure where practical

## Product scope

- This is a demo product, not a full enterprise platform.
- It should feel real, explainable, and useful.
- Deterministic recovery logic comes first. AI is layered on top.

## Data constraints

- Use synthetic but realistic ecommerce parcel and 3PL operational data.
- No real customer data is required.

## Code quality expectations

- Strong typing where practical
- Clear module boundaries
- README instructions for every major subsystem
- `.env.example` included
- Reasonable tests for core logic
