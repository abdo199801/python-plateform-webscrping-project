from __future__ import annotations

import os

from celery import Celery


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_celery_explicitly_enabled() -> bool:
    return is_truthy(os.getenv("ENABLE_CELERY", ""))


def get_celery_broker_url() -> str:
    return (
        os.getenv("CELERY_BROKER_URL", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or "redis://127.0.0.1:6379/0"
    )


def get_celery_result_backend() -> str:
    return (
        os.getenv("CELERY_RESULT_BACKEND", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or get_celery_broker_url()
    )


def is_celery_enabled() -> bool:
    return is_celery_explicitly_enabled() and bool(
        os.getenv("CELERY_BROKER_URL", "").strip() or os.getenv("REDIS_URL", "").strip()
    )


def get_queue_backend_name() -> str:
    return "celery" if is_celery_enabled() else "in-process"


celery_app = Celery(
    "mapsscraper",
    broker=get_celery_broker_url(),
    backend=get_celery_result_backend(),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
)