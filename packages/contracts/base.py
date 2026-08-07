"""Shared configuration for versioned data contracts."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTRACT_VERSION = "contracts.v0.1"


class BaseContract(BaseModel):
    """Strict, forward-compatible base for every persisted contract."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
        populate_by_name=True,
    )

    schema_version: str = Field(
        default=CONTRACT_VERSION,
        description="Contract version; serialized with every payload.",
    )
    contract_version: ClassVar[str] = CONTRACT_VERSION

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != cls.contract_version:
            raise ValueError(f"schema_version must equal {cls.contract_version}")
        return value
