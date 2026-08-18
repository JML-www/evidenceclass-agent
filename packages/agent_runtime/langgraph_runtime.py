"""LangGraph adapter for the deterministic classroom-analysis graph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .budget import BudgetLimits
from .planner import ConstrainedPlanner, MediaCapabilities, PlannerPolicyError
from .state import AgentState

LANGGRAPH_VERSION = "classroom-langgraph.v0.1"


class LangGraphState(TypedDict):
    agent_state: AgentState
    context: dict[str, Any]


def _updated(
    envelope: LangGraphState,
    node: str,
    trace: str,
    **updates: Any,
) -> dict[str, AgentState]:
    state = envelope["agent_state"]
    completed = list(state.completed_nodes)
    if node not in completed:
        completed.append(node)
    traces = [*state.trace, trace]
    return {
        "agent_state": state.model_copy(
            update={
                **updates,
                "graph_version": LANGGRAPH_VERSION,
                "current_node": node,
                "completed_nodes": completed,
                "trace": traces,
            }
        )
    }


def _simple_node(name: str, trace: str, **updates: Any) -> Callable[[LangGraphState], object]:
    def node(envelope: LangGraphState) -> object:
        return _updated(envelope, name, trace, **updates)

    return node


def build_langgraph(
    *,
    planner: ConstrainedPlanner | None = None,
    limits: BudgetLimits | None = None,
    checkpointer: InMemorySaver | None = None,
):
    """Compile typed nodes and conditional edges with a durable thread boundary."""

    planner = planner or ConstrainedPlanner()
    limits = limits or BudgetLimits()
    workflow = StateGraph(LangGraphState)

    workflow.add_node("initialize", _simple_node("initialize", "initialized"))
    workflow.add_node("inspect_assets", _simple_node("inspect_assets", "assets inspected"))
    workflow.add_node(
        "capability_router",
        _simple_node("capability_router", "capabilities routed"),
    )

    def plan(envelope: LangGraphState) -> object:
        state = envelope["agent_state"]
        context = envelope["context"]
        capabilities = MediaCapabilities(
            mode=state.mode,
            has_audio=bool(context.get("has_audio", False)),
            has_video=state.mode == "video",
            transcript_only=bool(context.get("transcript_only", False)),
            rubric_available=bool(context.get("rubric_available", False)),
            requested_identity=bool(context.get("requested_identity", False)),
            requested_full_frame=bool(context.get("requested_full_frame", False)),
            duration_seconds=int(context.get("duration_seconds", 0)),
        )
        try:
            accepted = planner.plan(goal=state.user_goal, capabilities=capabilities)
        except PlannerPolicyError as exc:
            return _updated(
                envelope,
                "plan",
                f"planner rejected: {exc}",
                final_status="FAILED",
            )
        return _updated(envelope, "plan", "structured plan accepted", plan=accepted)

    workflow.add_node("plan", plan)
    workflow.add_node("transcribe_audio", _simple_node("transcribe_audio", "audio transcribed"))
    workflow.add_node("ingest_transcript", _simple_node("ingest_transcript", "transcript ingested"))
    workflow.add_node("observe_image", _simple_node("observe_image", "image observed"))
    workflow.add_node("observe_media", _simple_node("observe_media", "media observed"))
    workflow.add_node(
        "validate_observations",
        _simple_node("validate_observations", "observations validated"),
    )

    def repair(envelope: LangGraphState) -> object:
        state = envelope["agent_state"]
        context = dict(envelope["context"])
        context["validation_error"] = False
        result = _updated(
            envelope,
            "repair_observations",
            "observations repaired",
            repair_rounds=state.repair_rounds + 1,
        )
        result["context"] = context
        return result

    workflow.add_node("repair_observations", repair)
    workflow.add_node("compute_metrics", _simple_node("compute_metrics", "metrics computed"))
    workflow.add_node("narrate_report", _simple_node("narrate_report", "report narrated"))
    workflow.add_node("verify_claims", _simple_node("verify_claims", "claims verified"))

    def revise(envelope: LangGraphState) -> object:
        state = envelope["agent_state"]
        context = dict(envelope["context"])
        if not context.get("persistent_verifier_failure", False):
            context["numeric_inconsistent"] = False
            context["verifier_failures"] = 0
        result = _updated(
            envelope,
            "revise_report",
            "report revised",
            repair_rounds=state.repair_rounds + 1,
        )
        result["context"] = context
        return result

    workflow.add_node("revise_report", revise)
    workflow.add_node(
        "create_review_items",
        _simple_node(
            "create_review_items",
            "human review requested",
            requires_review=True,
            final_status="NEEDS_REVIEW",
        ),
    )
    workflow.add_node(
        "publish_report",
        _simple_node("publish_report", "report published", final_status="SUCCEEDED"),
    )
    workflow.add_node(
        "fail_job",
        _simple_node("fail_job", "job failed", final_status="FAILED"),
    )

    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "inspect_assets")
    workflow.add_conditional_edges(
        "inspect_assets",
        lambda value: "fail" if value["context"].get("asset_valid", True) is False else "ok",
        {"fail": "fail_job", "ok": "capability_router"},
    )
    workflow.add_edge("capability_router", "plan")
    workflow.add_conditional_edges(
        "plan",
        lambda value: (
            "failed"
            if value["agent_state"].final_status == "FAILED"
            else "transcript"
            if value["context"].get("transcript_only", False)
            else "image"
            if value["agent_state"].mode == "image"
            else "audio"
            if value["agent_state"].mode == "video" and value["context"].get("has_audio", False)
            else "observe"
        ),
        {
            "failed": "fail_job",
            "transcript": "ingest_transcript",
            "image": "observe_image",
            "audio": "transcribe_audio",
            "observe": "observe_media",
        },
    )
    workflow.add_edge("transcribe_audio", "observe_media")
    workflow.add_edge("ingest_transcript", "narrate_report")
    workflow.add_edge("observe_image", "validate_observations")
    workflow.add_edge("observe_media", "validate_observations")
    workflow.add_conditional_edges(
        "validate_observations",
        lambda value: (
            "review"
            if value["context"].get("high_risk", False)
            else "repair"
            if value["context"].get("validation_error", False)
            and value["agent_state"].repair_rounds < limits.max_repair_rounds
            else "compute"
        ),
        {
            "review": "create_review_items",
            "repair": "repair_observations",
            "compute": "compute_metrics",
        },
    )
    workflow.add_edge("repair_observations", "validate_observations")
    workflow.add_edge("compute_metrics", "narrate_report")
    workflow.add_edge("narrate_report", "verify_claims")
    workflow.add_conditional_edges(
        "verify_claims",
        lambda value: (
            "publish"
            if not value["context"].get("numeric_inconsistent", False)
            and not value["context"].get("verifier_failures", 0)
            else "revise"
            if value["agent_state"].repair_rounds < limits.max_repair_rounds
            else "review"
        ),
        {
            "publish": "publish_report",
            "revise": "revise_report",
            "review": "create_review_items",
        },
    )
    workflow.add_edge("revise_report", "narrate_report")
    workflow.add_edge("create_review_items", END)
    workflow.add_edge("publish_report", END)
    workflow.add_edge("fail_job", END)
    return workflow.compile(checkpointer=checkpointer or InMemorySaver())


def invoke_langgraph(
    state: AgentState,
    *,
    context: dict[str, Any] | None = None,
    graph=None,
) -> AgentState:
    """Run one checkpointed thread and return the typed Agent state."""

    graph = graph or build_langgraph()
    result = graph.invoke(
        {"agent_state": state, "context": context or {}},
        {"configurable": {"thread_id": str(state.run_id)}},
    )
    return result["agent_state"]
