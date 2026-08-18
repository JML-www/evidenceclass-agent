"""Executable classroom Agent graph with explicit conditional edges.

The implementation is intentionally dependency-light: the graph contract is
usable in the offline CI environment and can be wrapped by LangGraph later
without changing node contracts or checkpoint semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .budget import BudgetExceeded, BudgetLimits, BudgetTracker
from .checkpoint import CheckpointStore
from .planner import ConstrainedPlanner, MediaCapabilities, PlannerPolicyError
from .state import AgentState

GRAPH_VERSION = "classroom-agent.v0.1"


class WorkerInterrupted(RuntimeError):
    """Raised by acceptance tests to simulate a worker restart."""


class GraphRunError(RuntimeError):
    code = "AGENT_GRAPH_FAILED"


def _update(state: AgentState, node: str, *, trace: str | None = None, **values: Any) -> AgentState:
    completed = list(state.completed_nodes)
    if node not in completed:
        completed.append(node)
    traces = list(state.trace)
    if trace:
        traces.append(trace)
    return state.model_copy(
        update={
            **values,
            "current_node": node,
            "completed_nodes": completed,
            "trace": traces,
            "graph_version": GRAPH_VERSION,
        }
    )


class AgentGraph:
    """A typed state graph whose route decisions are deterministic."""

    def __init__(
        self,
        *,
        planner: ConstrainedPlanner | None = None,
        checkpoints: CheckpointStore | None = None,
        budget_limits: BudgetLimits | None = None,
    ) -> None:
        self.planner = planner or ConstrainedPlanner()
        self.checkpoints = checkpoints or CheckpointStore()
        self.budget_limits = budget_limits or BudgetLimits()

    def route(self, state: AgentState, context: Mapping[str, Any] | None = None) -> str:
        context = context or {}
        node = state.current_node
        if node == "inspect_assets":
            return "fail_job" if context.get("asset_valid", True) is False else "capability_router"
        if node == "capability_router":
            if state.mode == "image":
                return "plan_image_analysis"
            if context.get("transcript_only", False):
                return "plan_transcript"
            return "plan_video_analysis"
        if node in {"plan_image_analysis", "plan_video_analysis", "plan_transcript"}:
            if node == "plan_transcript" or context.get("transcript_only", False):
                return "ingest_transcript"
            if node == "plan_image_analysis":
                return "observe_image"
            return (
                "transcribe_audio"
                if state.mode == "video" and context.get("has_audio", False)
                else "observe_media"
            )
        if node == "transcribe_audio":
            return "observe_media"
        if node == "ingest_transcript":
            return "narrate_report"
        if node == "observe_image":
            return "validate_observations"
        if node == "observe_media":
            return "validate_observations"
        if node == "validate_observations":
            if context.get("high_risk", False):
                return "create_review_items"
            if (
                context.get("validation_error", False)
                and state.repair_rounds < self.budget_limits.max_repair_rounds
            ):
                return "repair_observations"
            return "compute_metrics"
        if node == "repair_observations":
            return "validate_observations"
        if node == "compute_metrics":
            return "narrate_report"
        if node == "narrate_report":
            return "verify_claims"
        if node == "verify_claims":
            if (
                context.get("numeric_inconsistent", False)
                or context.get("verifier_failures", 0) > 0
            ):
                return (
                    "revise_report"
                    if state.repair_rounds < self.budget_limits.max_repair_rounds
                    else "create_review_items"
                )
            return "publish_report"
        if node == "revise_report":
            return "narrate_report"
        raise GraphRunError(f"no edge defined from node {node}")

    def run(
        self,
        state: AgentState,
        *,
        context: Mapping[str, Any] | None = None,
        crash_after: str | None = None,
        resume: bool = False,
    ) -> AgentState:
        context = context if isinstance(context, dict) else dict(context or {})
        if resume:
            state = self.checkpoints.restore(str(state.run_id))
            if state.requires_review:
                decision = context.get("review_decision")
                if decision in {"APPROVED", "MODIFIED"}:
                    state = state.model_copy(
                        update={
                            "requires_review": False,
                            "final_status": None,
                            "current_node": str(context.get("resume_node", "compute_metrics")),
                        }
                    )
                elif decision == "REJECTED":
                    failed = _update(
                        state,
                        "fail_job",
                        final_status="FAILED",
                        trace="human review rejected",
                    )
                    self.checkpoints.save_succeeded(failed, "fail_job")
                    return failed
                else:
                    return state
        tracker = BudgetTracker(self.budget_limits, usage=None)
        try:
            while True:
                node = state.current_node
                tracker.before_step()
                self.checkpoints.save_started(state, node)
                if node == "initialize":
                    state = _update(state, "initialize", trace="initialized")
                    next_node = "inspect_assets"
                elif node == "inspect_assets":
                    if context.get("asset_valid", True) is False:
                        state = _update(
                            state, node, final_status="FAILED", trace="asset inspection failed"
                        )
                        next_node = "fail_job"
                    else:
                        state = _update(state, node, trace="assets inspected")
                        next_node = "capability_router"
                elif node == "capability_router":
                    state = _update(state, node, trace="capabilities routed")
                    next_node = self.route(state, context)
                elif node in {"plan_image_analysis", "plan_video_analysis", "plan_transcript"}:
                    capabilities = MediaCapabilities(
                        mode="image" if node == "plan_image_analysis" else "video",
                        has_audio=bool(context.get("has_audio", False)),
                        has_video=state.mode == "video",
                        transcript_only=bool(context.get("transcript_only", False)),
                        rubric_available=bool(context.get("rubric_available", False)),
                        requested_identity=bool(context.get("requested_identity", False)),
                        requested_full_frame=bool(context.get("requested_full_frame", False)),
                        duration_seconds=int(context.get("duration_seconds", 0)),
                    )
                    try:
                        plan = self.planner.plan(
                            goal=state.user_goal,
                            capabilities=capabilities,
                        )
                    except PlannerPolicyError as exc:
                        state = _update(
                            state, node, final_status="FAILED", trace=f"planner rejected: {exc}"
                        )
                        next_node = "fail_job"
                    else:
                        state = _update(state, node, plan=plan, trace="structured plan accepted")
                        next_node = self.route(state, context)
                elif node == "transcribe_audio":
                    state = _update(state, node, trace="audio transcribed")
                    next_node = "observe_media"
                elif node in {"observe_media", "observe_image"}:
                    calls = int(context.get("vlm_calls", 0)) + 1
                    context["vlm_calls"] = calls
                    state = _update(
                        state, node, tool_calls=state.tool_calls + 1, trace="media observed"
                    )
                    next_node = "validate_observations"
                elif node == "ingest_transcript":
                    state = _update(state, node, trace="transcript ingested")
                    next_node = "narrate_report"
                elif node == "validate_observations":
                    state = _update(state, node, trace="observations validated")
                    next_node = self.route(state, context)
                elif node == "repair_observations":
                    tracker.before_repair()
                    state = _update(
                        state,
                        node,
                        repair_rounds=state.repair_rounds + 1,
                        trace="observations repaired",
                    )
                    context["validation_error"] = False
                    next_node = "validate_observations"
                elif node == "create_review_items":
                    state = _update(
                        state,
                        node,
                        requires_review=True,
                        final_status="NEEDS_REVIEW",
                        trace="human review requested",
                    )
                    self.checkpoints.save_succeeded(state, node)
                    return state
                elif node == "compute_metrics":
                    state = _update(state, node, trace="metrics computed")
                    next_node = "narrate_report"
                elif node == "narrate_report":
                    state = _update(state, node, trace="report narrated")
                    next_node = "verify_claims"
                elif node == "verify_claims":
                    state = _update(state, node, trace="claims verified")
                    next_node = self.route(state, context)
                elif node == "revise_report":
                    tracker.before_repair()
                    state = _update(
                        state, node, repair_rounds=state.repair_rounds + 1, trace="report revised"
                    )
                    context["numeric_inconsistent"] = False
                    context["verifier_failures"] = 0
                    next_node = "narrate_report"
                elif node == "publish_report":
                    if state.requires_review:
                        state = _update(
                            state,
                            node,
                            final_status="NEEDS_REVIEW",
                            trace="publication blocked by review",
                        )
                        self.checkpoints.save_succeeded(state, node)
                        return state
                    state = _update(state, node, final_status="SUCCEEDED", trace="report published")
                    self.checkpoints.save_succeeded(state, node)
                    return state
                elif node == "fail_job":
                    state = _update(state, node, final_status="FAILED", trace="job failed")
                    self.checkpoints.save_succeeded(state, node)
                    return state
                else:
                    raise GraphRunError(f"unknown node: {node}")
                state = state.model_copy(update={"current_node": next_node, "checkpoint_id": None})
                checkpoint = self.checkpoints.save_succeeded(
                    state, node, output=state.trace[-1] if state.trace else None
                )
                state = state.model_copy(update={"checkpoint_id": checkpoint.checkpoint_id})
                if crash_after == node:
                    raise WorkerInterrupted(f"worker interrupted after {node}")
        except BudgetExceeded as exc:
            failed = _update(
                state, state.current_node, final_status="BUDGET_EXCEEDED", trace=str(exc)
            )
            self.checkpoints.save_succeeded(failed, state.current_node)
            return failed


class AgentRuntime:
    def __init__(self, graph: AgentGraph | None = None) -> None:
        self.graph = graph or AgentGraph()

    def run(self, state: AgentState, *, context: Mapping[str, Any] | None = None) -> AgentState:
        return self.graph.run(state, context=context)

    def resume(self, state: AgentState, *, context: Mapping[str, Any] | None = None) -> AgentState:
        return self.graph.run(state, context=context, resume=True)


def build_agent_graph(**kwargs: Any) -> AgentGraph:
    return AgentGraph(**kwargs)
