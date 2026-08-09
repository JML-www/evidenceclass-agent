"""Small, versioned checkpoint state; large payloads stay in object storage."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

AGENT_STATE_VERSION = "agent-state.v0.1"


class StrictStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class CapabilitySnapshot(StrictStateModel):
    available_tools: list[str] = Field(default_factory=list)
    network_allowed: bool = False
    max_model_calls: NonNegativeInt = 0


class AnalysisPlan(StrictStateModel):
    goal: str
    steps: list[str] = Field(default_factory=list)
    deadline_seconds: NonNegativeInt


class ValidationIssue(StrictStateModel):
    code: str
    message: str
    source_ref: str | None = None


class RetryBudget(StrictStateModel):
    remaining_tool_retries: NonNegativeInt
    remaining_model_retries: NonNegativeInt


class AgentState(StrictStateModel):
    schema_version: Literal["agent-state.v0.1"] = AGENT_STATE_VERSION
    run_id: UUID
    job_id: UUID
    user_goal: str
    mode: Literal["image", "video", "structured"]
    asset_ids: list[UUID] = Field(default_factory=list)
    capabilities: CapabilitySnapshot
    plan: AnalysisPlan | None = None
    retrieved_chunk_ids: list[UUID] = Field(default_factory=list)
    observation_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[UUID] = Field(default_factory=list)
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    retry_budget: RetryBudget
    requires_review: bool = False
    final_status: str | None = None
