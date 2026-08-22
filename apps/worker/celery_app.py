"""Celery entry point; the API can use the local queue when no broker is configured."""

from __future__ import annotations

import os

from celery import Celery

celery_app = Celery(
    "evidenceclass_agent",
    broker=os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")),
    backend=os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")),
)
celery_app.conf.update(
    task_track_started=True, task_acks_late=True, task_reject_on_worker_lost=True
)


@celery_app.task(name="evidenceclass.run_agent")
def run_agent(run_id: str) -> str:
    """Production deployment hook; the API's app factory registers a concrete worker."""

    # A Celery process should construct its own database session factory from env.
    from apps.worker.runtime_bootstrap import build_worker

    result = build_worker().run(run_id)
    return str(result.get("status", "UNKNOWN"))
