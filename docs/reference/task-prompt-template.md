# Task Prompt Template

Use this template when assigning a scoped implementation task:

```text
You are implementing one scoped task in the ParcelOps Recovery Copilot demo project.

Whole picture:
This product helps ecommerce operators recover lost money and reduce operational waste across parcel and 3PL networks. Users upload messy logistics data, the system normalizes it, detects billing issues, shows recoverable dollars, explains why issues happened, and helps create dispute-ready actions.

Global constraints:
- Run locally with Docker Compose only
- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- DB: Postgres
- Background jobs: Celery + Redis
- Synthetic demo data only
- Keep solutions simple and production-minded

Current task:
[PASTE TASK HERE]

Please implement only this task, keep the scope tight, update docs as needed, and include any minimal tests that make sense.
```
