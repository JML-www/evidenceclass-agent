from time import sleep
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from packages.agent_runtime import (
    AgentClaim,
    AgentGraph,
    AgentState,
    CapabilitySnapshot,
    CheckpointStore,
    ClaimVerifier,
    ConstrainedPlanner,
    MediaCapabilities,
    PlannerPolicyError,
    RetryBudget,
    ReviewError,
    ReviewService,
    ToolRegistry,
    ToolRegistryError,
    ToolTimeoutError,
    WorkerInterrupted,
    build_langgraph,
    invoke_langgraph,
)


def make_state(mode: str = "video", tools: list[str] | None = None) -> AgentState:
    return AgentState(
        run_id=uuid4(),
        job_id=uuid4(),
        user_goal="analyze classroom evidence",
        mode=mode,
        capabilities=CapabilitySnapshot(
            available_tools=tools or ["inspect_media", "observe_media"]
        ),
        retry_budget=RetryBudget(remaining_tool_retries=2, remaining_model_retries=1),
    )


def test_graph_skips_asr_for_video_without_audio():
    state = make_state()
    result = AgentGraph().run(state, context={"has_audio": False})
    assert result.final_status == "SUCCEEDED"
    assert "transcribe_audio" not in result.completed_nodes


def test_graph_routes_image_without_video_tools():
    state = make_state("image", ["inspect_media", "observe_image"])
    result = AgentGraph().run(state, context={})
    assert result.final_status == "SUCCEEDED"
    assert "plan_image_analysis" in result.completed_nodes
    assert "transcribe_audio" not in result.completed_nodes


def test_graph_stops_for_high_risk_review():
    graph = AgentGraph()
    state = make_state()
    result = graph.run(state, context={"high_risk": True})
    assert result.final_status == "NEEDS_REVIEW"
    assert result.requires_review is True
    assert result.current_node == "create_review_items"
    resumed = graph.run(
        state,
        context={"review_decision": "APPROVED"},
        resume=True,
    )
    assert resumed.final_status == "SUCCEEDED"
    assert resumed.requires_review is False


@pytest.mark.parametrize(
    ("mode", "context", "expected", "absent"),
    [
        ("video", {"has_audio": True}, "transcribe_audio", None),
        ("video", {"has_audio": False}, "observe_media", "transcribe_audio"),
        ("image", {}, "observe_image", "transcribe_audio"),
    ],
)
def test_langgraph_runs_three_conditioned_trajectories(mode, context, expected, absent):
    state = make_state(mode)
    graph = build_langgraph()
    result = invoke_langgraph(state, context=context, graph=graph)
    assert result.final_status == "SUCCEEDED"
    assert expected in result.completed_nodes
    if absent:
        assert absent not in result.completed_nodes
    snapshot = graph.get_state({"configurable": {"thread_id": str(state.run_id)}})
    assert snapshot.values["agent_state"].graph_version == "classroom-langgraph.v0.1"


def test_transcript_only_plan_skips_media_observation():
    result = invoke_langgraph(make_state("structured"), context={"transcript_only": True})
    assert result.final_status == "SUCCEEDED"
    assert "ingest_transcript" in result.completed_nodes
    assert "observe_media" not in result.completed_nodes


def test_langgraph_persistent_verifier_failure_stops_at_repair_budget():
    result = invoke_langgraph(
        make_state(),
        context={"verifier_failures": 1, "persistent_verifier_failure": True},
    )
    assert result.final_status == "NEEDS_REVIEW"
    assert result.repair_rounds == 2
    assert "create_review_items" in result.completed_nodes


def test_checkpoint_resume_does_not_repeat_observation():
    checkpoints = CheckpointStore()
    graph = AgentGraph(checkpoints=checkpoints)
    state = make_state()
    context = {"has_audio": True}
    with pytest.raises(WorkerInterrupted):
        graph.run(state, context=context, crash_after="observe_media")
    assert context["vlm_calls"] == 1
    result = graph.run(state, context=context, resume=True)
    assert result.final_status == "SUCCEEDED"
    assert context["vlm_calls"] == 1
    assert (
        len(
            [
                r
                for r in checkpoints.records(str(state.run_id))
                if r.node == "observe_media" and r.status == "SUCCEEDED"
            ]
        )
        == 1
    )


def test_planner_policy_rejects_identity_and_long_full_frame():
    planner = ConstrainedPlanner()
    with pytest.raises(PlannerPolicyError):
        planner.plan(
            goal="identify students",
            capabilities=MediaCapabilities(mode="video", requested_identity=True),
        )
    with pytest.raises(PlannerPolicyError):
        planner.plan(
            goal="scan every frame",
            capabilities=MediaCapabilities(
                mode="video", requested_full_frame=True, duration_seconds=901
            ),
        )


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workspace_id: str
    value: int


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    accepted: bool


def test_tool_registry_enforces_registration_schema_workspace_and_idempotency():
    calls = []
    registry = ToolRegistry()
    registry.register(
        name="safe_tool",
        version="1.0.0",
        input_model=Input,
        output_model=Output,
        handler=lambda payload: calls.append(payload.value) or {"accepted": True},
    )
    first = registry.invoke(
        "safe_tool", {"workspace_id": "A", "value": 1}, workspace_id="A", idempotency_key="k"
    )
    second = registry.invoke(
        "safe_tool", {"workspace_id": "A", "value": 1}, workspace_id="A", idempotency_key="k"
    )
    assert first.output.accepted and second.cached and calls == [1]
    with pytest.raises(ToolRegistryError, match="unregistered"):
        registry.invoke("shell", {}, workspace_id="A")
    with pytest.raises(ToolRegistryError, match="workspace"):
        registry.invoke("safe_tool", {"workspace_id": "B", "value": 1}, workspace_id="A")
    with pytest.raises(ToolRegistryError):
        registry.invoke(
            "safe_tool", {"workspace_id": "A", "value": 1, "path": ".."}, workspace_id="A"
        )


def test_tool_registry_enforces_timeout():
    registry = ToolRegistry()
    registry.register(
        name="slow_tool",
        version="1.0.0",
        input_model=Input,
        output_model=Output,
        timeout_seconds=1,
        handler=lambda _payload: sleep(1.1) or {"accepted": True},
    )
    with pytest.raises(ToolTimeoutError, match="timed out"):
        registry.invoke("slow_tool", {"workspace_id": "A", "value": 1}, workspace_id="A")


def test_review_service_requires_role_and_is_single_decision():
    service = ReviewService()
    item = service.create(job_id=uuid4(), reason="ambiguous", risk="HIGH", observation={"x": 1})
    with pytest.raises(ReviewError):
        service.decide(item.review_id, reviewer_id="u", role="viewer", decision="APPROVED")
    decided = service.decide(
        item.review_id,
        reviewer_id="u",
        role="reviewer",
        decision="MODIFIED",
        revised_observation={"x": 2},
    )
    assert decided.original_observation == {"x": 1}
    assert decided.revised_observation == {"x": 2}
    with pytest.raises(ReviewError):
        service.decide(item.review_id, reviewer_id="u", role="reviewer", decision="APPROVED")


def test_claim_verifier_rejects_contaminated_claims():
    claims = [
        AgentClaim(claim_id="missing", text="students focused", evidence_ids=["e2"]),
        AgentClaim(claim_id="number", text="focus 99%", evidence_ids=["e1"], numbers=[99]),
        AgentClaim(claim_id="causal", text="because the teacher caused focus", evidence_ids=["e1"]),
        AgentClaim(claim_id="psych", text="student motivation is low", evidence_ids=["e1"]),
        AgentClaim(claim_id="image", text="whole lesson", evidence_ids=["e1"], scope="lesson"),
    ]
    result = ClaimVerifier().verify(
        claims,
        workspace_id="w",
        evidence_ids={"e1"},
        analysis_result={"focus": 0.5},
        mode="image",
    )
    assert not result.publishable
    assert {issue.code for issue in result.issues} >= {
        "UNKNOWN_EVIDENCE",
        "NUMBER_NOT_IN_RESULT",
        "UNSUPPORTED_CAUSALITY",
        "PSYCHOLOGICAL_INFERENCE",
        "IMAGE_SCOPE_ESCALATION",
    }
