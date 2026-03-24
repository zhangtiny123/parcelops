FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
COPY apps/worker/requirements.txt /app/apps/worker/requirements.txt
RUN pip install -r /app/apps/worker/requirements.txt

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

WORKDIR /app/apps/worker
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

CMD ["celery", "-A", "worker_app", "worker", "--loglevel=INFO"]
