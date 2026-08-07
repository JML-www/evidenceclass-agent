"""Sourced evaluation rubric contracts."""

from pydantic import Field, NonNegativeFloat, ValidationInfo, field_validator, model_validator

from .base import BaseContract


class RubricTarget(BaseContract):
    """Optional min/max target for one metric."""

    minimum: NonNegativeFloat | None = Field(default=None, description="Minimum target value.")
    maximum: NonNegativeFloat | None = Field(default=None, description="Maximum target value.")

    @model_validator(mode="after")
    def validate_range(self) -> "RubricTarget":
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class EvaluationRubric(BaseContract):
    """A versioned, attributable scoring rubric; missing source means unknown score."""

    name: str = Field(min_length=1, description="Rubric name.")
    version: str = Field(min_length=1, description="Rubric version.")
    source: str | None = Field(default=None, description="Citation or URI for the rubric source.")
    weights: dict[str, NonNegativeFloat] = Field(
        default_factory=dict, description="Metric weights; values are non-negative."
    )
    targets: dict[str, RubricTarget] = Field(
        default_factory=dict, description="Metric target ranges."
    )
    overall: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Weighted score in 0..100; null when no sourced rubric is available.",
    )

    @field_validator("overall")
    @classmethod
    def validate_source_before_score(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        if info.data.get("source") is None and value is not None:
            raise ValueError("overall must be null when rubric.source is null")
        return value
