from uuid import uuid4

from sqlalchemy import select

from packages.model_gateway.contracts import ModelUsage
from packages.model_gateway.recording import SqlAlchemyModelCallRecorder
from packages.model_gateway.resilience import AttemptRecord
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import (
    AgentRun,
    AgentStep,
    AnalysisJob,
    ModelCall,
    ToolCall,
    User,
    Workspace,
)


def test_every_success_and_failure_attempt_is_sanitized_and_persisted(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'model-calls.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    ids = {name: uuid4() for name in ("user", "workspace", "job", "run", "step", "tool")}
    with sessions() as session, session.begin():
        session.add(
            User(id=ids["user"], email="calls@example.test", password_hash="synthetic")
        )
        session.flush()
        session.add(Workspace(id=ids["workspace"], name="calls", owner_id=ids["user"]))
        session.flush()
        session.add(
            AnalysisJob(
                id=ids["job"],
                workspace_id=ids["workspace"],
                mode="image",
                status="RUNNING",
            )
        )
        session.flush()
        session.add(
            AgentRun(
                id=ids["run"],
                job_id=ids["job"],
                graph_version="test",
                status="EXECUTING",
                budget_json={},
                active_slot="active",
            )
        )
        session.flush()
        session.add(
            AgentStep(
                id=ids["step"], run_id=ids["run"], node="observe", status="STARTED"
            )
        )
        session.flush()
        session.add(
            ToolCall(
                id=ids["tool"],
                step_id=ids["step"],
                tool_name="observe_visuals",
                args_json={"body_logged": False},
                status="STARTED",
                attempt=1,
            )
        )

    recorder = SqlAlchemyModelCallRecorder(sessions, tool_call_id=ids["tool"])
    common = {
        "provider": "fake",
        "model": "fake-vision",
        "model_revision": "fixture.v1",
        "prompt_version": "prompt.v1",
        "config_version": "config.v1",
    }
    recorder.record(
        AttemptRecord(
            **common,
            attempt=1,
            status="FAILED",
            error_code="MODEL_RATE_LIMITED",
            usage=None,
            latency_ms=2.0,
            raw_response_ref=None,
        )
    )
    recorder.record(
        AttemptRecord(
            **common,
            attempt=2,
            status="SUCCEEDED",
            error_code=None,
            usage=ModelUsage(
                input_tokens=12,
                output_tokens=8,
                characters=100,
                audio_seconds=0.0,
                cost_usd=0.002,
            ),
            latency_ms=3.0,
            raw_response_ref="object://workspace/job/raw/response.json",
        )
    )
    with sessions() as session:
        rows = list(session.scalars(select(ModelCall).order_by(ModelCall.attempt)))
    assert [row.status for row in rows] == ["FAILED", "SUCCEEDED"]
    assert rows[0].error_code == "MODEL_RATE_LIMITED"
    assert rows[0].cost is None and rows[0].cost_known is False
    assert rows[1].cost == 0.002 and rows[1].cost_known is True
    assert rows[1].raw_response_ref.startswith("object://")
    assert not hasattr(rows[1], "prompt_body")
    assert not hasattr(rows[1], "image_bytes")
    engine.dispose()
