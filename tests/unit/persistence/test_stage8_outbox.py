from uuid import UUID, uuid4

from packages.persistence import Base, OutboxPublisher, create_db_engine, make_session_factory
from packages.persistence.jobs import JobLifecycleService
from packages.persistence.models import OutboxEvent, User, Workspace


def test_outbox_retries_then_publishes_once(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'outbox.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(User(id=user_id, email="outbox@example.test", password_hash="fixture"))
        session.flush()
        session.add(Workspace(id=workspace_id, name="outbox", owner_id=user_id))
    lifecycle = JobLifecycleService(sessions)
    job = lifecycle.create_job(
        workspace_id=workspace_id,
        mode="image",
        idempotency_key="outbox-create",
    )
    started = lifecycle.start_job(
        workspace_id=workspace_id,
        job_id=UUID(job["job_id"]),
        idempotency_key="outbox-start",
    )
    publisher = OutboxPublisher(sessions)
    calls = []

    def fail_once(topic, aggregate_id, payload):
        calls.append((topic, aggregate_id, payload))
        if len(calls) == 1:
            raise RuntimeError("broker offline")

    assert publisher.publish_pending(fail_once) == []
    published = publisher.publish_pending(fail_once)
    assert len(published) == 1
    assert calls[-1][0] == "agent.run.requested"
    assert calls[-1][1] == UUID(started["run_id"])
    assert publisher.publish_pending(fail_once) == []
    with sessions() as session:
        event = session.get(OutboxEvent, published[0])
        assert event.status == "PUBLISHED"
        assert event.attempts == 2
        assert event.last_error == "broker offline"
    engine.dispose()
