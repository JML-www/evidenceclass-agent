from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from packages.agent_runtime import (
    AgentRunEvent,
    AgentRunState,
    InvalidTransition,
    JobEvent,
    JobState,
    ReviewDecision,
)
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.idempotency import IdempotencyConflict
from packages.persistence.jobs import JobLifecycleService
from packages.persistence.models import (
    AgentRun,
    AnalysisJob,
    IdempotencyRecord,
    ReviewItem,
    User,
    Workspace,
    WorkspaceMember,
)


def _service(tmp_path):
    url = f"sqlite:///{(tmp_path / 'idempotency.db').as_posix()}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.test",
                password_hash="not-a-real-password-hash",
            )
        )
        session.add(Workspace(id=workspace_id, name="test", owner_id=user_id))
        session.add(
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER")
        )
    return engine, sessions, JobLifecycleService(sessions), workspace_id


def test_fifty_concurrent_identical_creates_produce_one_job(tmp_path):
    engine, sessions, service, workspace_id = _service(tmp_path)

    def create(_index):
        return service.create_job(
            workspace_id=workspace_id,
            mode="video",
            idempotency_key="same-create-key",
            request={"goal": "same request"},
        )

    with ThreadPoolExecutor(max_workers=50) as pool:
        responses = list(pool.map(create, range(50)))

    assert len({response["job_id"] for response in responses}) == 1
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
    engine.dispose()


def test_same_key_with_different_request_returns_conflict(tmp_path):
    engine, _sessions, service, workspace_id = _service(tmp_path)
    service.create_job(
        workspace_id=workspace_id,
        mode="image",
        idempotency_key="reused-key",
    )
    with pytest.raises(IdempotencyConflict) as error:
        service.create_job(
            workspace_id=workspace_id,
            mode="video",
            idempotency_key="reused-key",
        )
    assert error.value.status_code == 409
    engine.dispose()


def test_fifty_concurrent_identical_starts_produce_one_active_run(tmp_path):
    engine, sessions, service, workspace_id = _service(tmp_path)
    job = service.create_job(
        workspace_id=workspace_id,
        mode="structured",
        idempotency_key="create-before-start",
    )
    job_id = UUID(job["job_id"])

    def start(_index):
        return service.start_job(
            workspace_id=workspace_id,
            job_id=job_id,
            idempotency_key="same-start-key",
        )

    with ThreadPoolExecutor(max_workers=50) as pool:
        responses = list(pool.map(start, range(50)))

    assert len({response["run_id"] for response in responses}) == 1
    repeated_with_another_key = service.start_job(
        workspace_id=workspace_id,
        job_id=job_id,
        idempotency_key="different-retry-key",
    )
    assert repeated_with_another_key["run_id"] == responses[0]["run_id"]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.active_slot == "active")
            )
            == 1
        )
    engine.dispose()


def test_repository_preserves_cancellation_and_requires_persisted_review(tmp_path):
    engine, sessions, service, workspace_id = _service(tmp_path)
    job = service.create_job(
        workspace_id=workspace_id,
        mode="structured",
        idempotency_key="lifecycle-create",
    )
    job_id = UUID(job["job_id"])
    started = service.start_job(
        workspace_id=workspace_id,
        job_id=job_id,
        idempotency_key="lifecycle-start",
    )
    run_id = UUID(started["run_id"])

    assert (
        service.apply_job_event(
            workspace_id=workspace_id,
            job_id=job_id,
            event=JobEvent.WORKER_STARTED,
        )
        is JobState.RUNNING
    )
    assert (
        service.apply_job_event(
            workspace_id=workspace_id,
            job_id=job_id,
            event=JobEvent.CANCEL,
        )
        is JobState.CANCELLED
    )
    assert (
        service.apply_job_event(
            workspace_id=workspace_id,
            job_id=job_id,
            event=JobEvent.SUCCEED,
        )
        is JobState.CANCELLED
    )

    for event, expected in (
        (AgentRunEvent.INSPECT, AgentRunState.INSPECTING),
        (AgentRunEvent.PLAN, AgentRunState.PLANNING),
        (AgentRunEvent.EXECUTE, AgentRunState.EXECUTING),
        (AgentRunEvent.REQUEST_REVIEW, AgentRunState.WAITING_HUMAN),
    ):
        assert service.apply_run_event(run_id=run_id, event=event) is expected
    with pytest.raises(InvalidTransition, match="recorded review decision"):
        service.apply_run_event(
            run_id=run_id,
            event=AgentRunEvent.RESUME,
            review_decision=ReviewDecision.APPROVED,
        )

    with sessions() as session, session.begin():
        session.add(
            ReviewItem(
                job_id=job_id,
                reason="synthetic ambiguity",
                risk="LOW",
                status="DECIDED",
                decision=ReviewDecision.APPROVED.value,
            )
        )
    assert (
        service.apply_run_event(run_id=run_id, event=AgentRunEvent.RESUME)
        is AgentRunState.EXECUTING
    )
    assert (
        service.apply_run_event(run_id=run_id, event=AgentRunEvent.VERIFY)
        is AgentRunState.VERIFYING
    )
    assert (
        service.apply_run_event(run_id=run_id, event=AgentRunEvent.COMPLETE)
        is AgentRunState.COMPLETED
    )
    with sessions() as session:
        assert session.get(AgentRun, run_id).active_slot is None
    engine.dispose()
