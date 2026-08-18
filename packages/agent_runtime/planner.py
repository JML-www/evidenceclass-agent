"""Structured, policy-constrained planning without free-form execution."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from .state import AnalysisPlan


class PlannerPolicyError(ValueError):
    code = "PLANNER_POLICY_REJECTED"


class MediaCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: str
    has_audio: bool = False
    has_video: bool = False
    transcript_only: bool = False
    rubric_available: bool = False
    requested_identity: bool = False
    requested_full_frame: bool = False
    duration_seconds: NonNegativeInt = 0


class PlannerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allowed_steps: set[str] = Field(
        default_factory=lambda: {
            "inspect_media",
            "extract_frames",
            "transcribe_audio",
            "ingest_transcript",
            "observe_image",
            "observe_media",
            "retrieve_knowledge",
            "validate_observations",
            "repair_observations",
            "compute_metrics",
            "narrate_report",
            "verify_claims",
            "publish_report",
        }
    )
    max_steps: NonNegativeInt = 12
    allow_identity: bool = False
    max_full_frame_seconds: NonNegativeInt = 900


class ConstrainedPlanner:
    def __init__(self, policy: PlannerPolicy | None = None) -> None:
        self.policy = policy or PlannerPolicy()

    def plan(
        self,
        *,
        goal: str,
        capabilities: MediaCapabilities,
        tool_names: set[str] | frozenset[str] | None = None,
        prompt_version: str = "planner.v0.1",
    ) -> AnalysisPlan:
        if capabilities.requested_identity and not self.policy.allow_identity:
            raise PlannerPolicyError("identity recognition is outside the classroom policy")
        if (
            capabilities.requested_full_frame
            and capabilities.duration_seconds > self.policy.max_full_frame_seconds
        ):
            raise PlannerPolicyError("full-frame analysis exceeds the configured media budget")
        if capabilities.transcript_only:
            steps = ["ingest_transcript"]
        elif capabilities.mode == "image":
            steps = ["inspect_media", "observe_image"]
        elif capabilities.mode == "video":
            steps = ["inspect_media", "extract_frames"]
            if capabilities.has_audio:
                steps.append("transcribe_audio")
            steps.append("observe_media")
        else:
            steps = ["inspect_media"]
        if capabilities.rubric_available:
            steps.append("retrieve_knowledge")
        steps.extend(
            [
                "validate_observations",
                "compute_metrics",
                "narrate_report",
                "verify_claims",
                "publish_report",
            ]
        )
        invalid = [step for step in steps if step not in self.policy.allowed_steps]
        if invalid:
            raise PlannerPolicyError(f"steps are not permitted: {', '.join(invalid)}")
        if len(steps) > self.policy.max_steps:
            raise PlannerPolicyError("plan exceeds max_steps")
        if tool_names is not None:
            missing = sorted(
                {
                    step
                    for step in steps
                    if step
                    in {
                        "inspect_media",
                        "extract_frames",
                        "transcribe_audio",
                        "observe_image",
                        "observe_media",
                        "retrieve_knowledge",
                    }
                    and step not in tool_names
                }
            )
            if missing:
                raise PlannerPolicyError(f"plan requires unregistered tools: {', '.join(missing)}")
        return AnalysisPlan(
            goal=goal,
            steps=steps,
            deadline_seconds=300 if capabilities.mode != "video" else 900,
            tools=[
                step
                for step in steps
                if step
                not in {
                    "validate_observations",
                    "compute_metrics",
                    "narrate_report",
                    "verify_claims",
                    "publish_report",
                }
            ],
            policy_notes=["identity recognition disabled", "full-frame budget enforced"],
            prompt_version=prompt_version,
        )


Planner = ConstrainedPlanner
