from datetime import datetime, timezone
from uuid import uuid4


def generate_uuid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
