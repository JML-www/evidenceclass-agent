from uuid import uuid4

import pytest

from packages.agent_runtime import (
    AgentState,
    CapabilitySnapshot,
    RetryBudget,
    ReviewError,
)
from packages.agent_runtime.state import AnalysisPlan
from packages.persistence import (
    Base,
    SqlCheckpointStore,
    SqlReviewService,
    create_db_engine,
    make_session_factory,
)
from packages.persistence.models import (
    AgentRun,
    AnalysisJob,
    ReviewItem,
    User,
    Workspace,
)


def runtime_database(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'stage7.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id, job_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(User(id=user_id, email="stage7@example.test", password_hash="hash"))
        session.flush()
        session.add(Workspace(id=workspace_id, name="stage7", owner_id=user_id))
        session.flush()
        session.add(
            AnalysisJob(
                id=job_id,
                workspace_id=workspace_id,
                mode="video",
                status="RUNNING",
            )
        )
        session.flush()
        session.add(
            AgentRun(
                id=run_id,
                job_id=job_id,
                graph_version="classroom-agent.v0.1",
                status="EXECUTING",
                budget_json={},
            )
        )
    return engine, sessions, job_id, run_id


def test_sql_checkpoint_restores_state_and_persists_plan_prompt(tmp_path):
    engine, sessions, job_id, run_id = runtime_database(tmp_path)
    state = AgentState(
        run_id=run_id,
        job_id=job_id,
        user_goal="analyze",
        mode="video",
        capabilities=CapabilitySnapshot(),
        retry_budget=RetryBudget(remaining_tool_retries=1, remaining_model_retries=1),
        plan=AnalysisPlan(
            goal="analyze",
            steps=["observe_media"],
            deadline_seconds=300,
            prompt_version="planner.test",
        ),
        current_node="observe_media",
    )
    checkpoints = SqlCheckpointStore(sessions)
    checkpoints.save_started(state, "observe_media")
    checkpoint = checkpoints.save_succeeded(state, "observe_media", {"ok": True})

    restored = checkpoints.restore(str(run_id))
    assert restored == state
    assert checkpoint.output_hash is not None
    with sessions() as session:
        run = session.get(AgentRun, run_id)
        assert run.checkpoint_id == checkpoint.checkpoint_id
        assert run.graph_version == "classroom-agent.v0.1"
        assert run.prompt_version == "planner.test"
        assert run.plan_json["steps"] == ["observe_media"]
    engine.dispose()


def test_sql_review_is_authorized_single_decision_and_keeps_original(tmp_path):
    engine, sessions, job_id, _run_id = runtime_database(tmp_path)
    reviews = SqlReviewService(sessions)
    review_id = reviews.create(
        job_id=job_id,
        reason="ambiguous frame",
        risk="HIGH",
        observation={"visible": 1},
    )
    with pytest.raises(ReviewError, match="role"):
        reviews.decide(
            review_id,
            reviewer_id="viewer",
            role="viewer",
            decision="APPROVED",
        )
    reviews.decide(
        review_id,
        reviewer_id="reviewer-1",
        role="reviewer",
        decision="MODIFIED",
        note="corrected occlusion",
        revised_observation={"visible": 2},
    )
    with pytest.raises(ReviewError, match="already"):
        reviews.decide(
            review_id,
            reviewer_id="reviewer-2",
            role="reviewer",
            decision="APPROVED",
        )
    with sessions() as session:
        item = session.get(ReviewItem, review_id)
        assert item.original_payload_json == {"visible": 1}
        assert item.revised_payload_json == {"visible": 2}
        assert item.reviewer_id == "reviewer-1"
        assert item.revision == 1
    engine.dispose()
