# Runtime Target

The Docker Compose stack should eventually include these services:

- `web`: Next.js app
- `api`: FastAPI app
- `worker`: Celery worker
- `postgres`
- `redis`

Optional services:

- `flower` for Celery inspection
- `pgadmin` if it proves helpful

All services should boot from one command:

```bash
docker compose up --build
```
