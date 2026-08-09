import socket
from uuid import uuid4

from sqlalchemy import select

from packages.evidence_engine import ARTIFACT_FILENAMES
from packages.model_gateway.acceptance_harness import FakeStage4AcceptanceHarness
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import AgentRun, AnalysisJob, ModelCall, User, Workspace


def test_offline_fake_job_to_agent_trace_to_five_artifacts(tmp_path, monkeypatch):
    def deny_network(*_args, **_kwargs):
        raise AssertionError("offline Fake acceptance attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'fake-e2e.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(User(id=user_id, email="fake-e2e@example.test", password_hash="synthetic"))
        session.flush()
        session.add(Workspace(id=workspace_id, name="offline", owner_id=user_id))

    output = tmp_path / "five artifacts"
    result = FakeStage4AcceptanceHarness(sessions).run(
        workspace_id=workspace_id,
        output_dir=output,
    )
    assert tuple(result.engine_summary.artifacts) == ARTIFACT_FILENAMES
    assert {path.name for path in output.iterdir()} == set(ARTIFACT_FILENAMES)
    with sessions() as session:
        job = session.get(AnalysisJob, result.job_id)
        run = session.get(AgentRun, result.run_id)
        model_call = session.scalar(
            select(ModelCall).where(ModelCall.tool_call_id == result.tool_call_id)
        )
        assert job.status == "SUCCEEDED"
        assert run.status == "COMPLETED"
        assert run.active_slot is None
        assert model_call.status == "SUCCEEDED"
        assert model_call.provider == "fake"
        assert model_call.raw_response_ref.startswith("fixture://")
        assert model_call.input_tokens == 10
        assert model_call.output_tokens == 20
        assert model_call.cost_known is True
    engine.dispose()
