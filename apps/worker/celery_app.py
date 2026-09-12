"""Celery entry point; the API can use the local queue when no broker is configured."""

from __future__ import annotations

import os
from typing import Any

from celery import Celery

from packages.observability import CorrelationContext, bind

celery_app = Celery(
    "evidenceclass_agent",
    broker=os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")),
    backend=os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")),
)
celery_app.conf.update(
    task_track_started=True, task_acks_late=True, task_reject_on_worker_lost=True
)


def _context_from_request(task: Any) -> CorrelationContext | None:
    """Rebuild the correlation scope from the task headers, if any."""

    headers = getattr(getattr(task, "request", None), "headers", None)
    if not headers:
        return None
    return CorrelationContext.from_headers(headers)


@celery_app.task(bind=True, name="evidenceclass.run_agent")
def run_agent(self: Any, run_id: str) -> str:
    """Production deployment hook; the API's app factory registers a concrete worker."""

    # A Celery process should construct its own database session factory from env.
    from apps.worker.runtime_bootstrap import build_worker

    with bind(_context_from_request(self)):
        result = build_worker().run(run_id)
    return str(result.get("status", "UNKNOWN"))


@celery_app.task(bind=True, name="evidenceclass.resume_agent")
def resume_agent(self: Any, run_id: str, decision: str) -> str:
    """Resume a persisted human-review checkpoint after an audited decision."""

    from apps.worker.runtime_bootstrap import build_worker

    with bind(_context_from_request(self)):
        result = build_worker().resume(run_id, decision)
    return str(result.get("status", "UNKNOWN"))
