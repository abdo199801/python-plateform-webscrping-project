from __future__ import annotations

from fastapi import BackgroundTasks

from app.celery_app import celery_app, get_queue_backend_name, is_celery_enabled
from app.services import process_scrape_run


@celery_app.task(name="app.tasks.run_scrape_run")
def run_scrape_run_task(run_id: int, payload: dict, user_email: str) -> None:
    process_scrape_run(run_id, payload, user_email)


def dispatch_scrape_run(background_tasks: BackgroundTasks, run_id: int, payload: dict, user_email: str) -> str:
    if is_celery_enabled():
        run_scrape_run_task.delay(run_id, payload, user_email)
        return "celery"

    background_tasks.add_task(process_scrape_run, run_id, payload, user_email)
    return "in-process"


def get_task_queue_backend() -> str:
    return get_queue_backend_name()