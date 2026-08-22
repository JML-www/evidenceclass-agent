import os
from uuid import UUID, uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import select

from apps.worker.celery_app import celery_app, run_agent
from packages.persistence import create_db_engine, make_session_factory
from packages.persistence.jobs import JobLifecycleService
from packages.persistence.models import AnalysisJob, User, Workspace

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGE8_CELERY_TESTS") != "1",
    reason="requires migrated PostgreSQL and Redis broker",
)


def test_celery_worker_claims_persisted_run_and_completes_once():
    engine = create_db_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"stage8-{user_id}@example.test",
                password_hash="fixture-only",
            )
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="stage8-celery", owner_id=user_id))
    lifecycle = JobLifecycleService(sessions)
    job = lifecycle.create_job(
        workspace_id=workspace_id,
        mode="image",
        idempotency_key=f"create-{uuid4()}",
    )
    started = lifecycle.start_job(
        workspace_id=workspace_id,
        job_id=UUID(job["job_id"]),
        idempotency_key=f"start-{uuid4()}",
    )
    with start_worker(celery_app, perform_ping_check=False, pool="solo", concurrency=1):
        result = run_agent.delay(started["run_id"])
        assert result.get(timeout=30) == "COMPLETED"
        duplicate = run_agent.delay(started["run_id"])
        assert duplicate.get(timeout=30) == "SKIPPED"
    with sessions() as session:
        persisted = session.scalar(
            select(AnalysisJob).where(AnalysisJob.id == UUID(job["job_id"]))
        )
        assert persisted.status == "SUCCEEDED"
        assert persisted.progress == 100
    engine.dispose()
