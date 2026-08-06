# packages/contracts/base.py
from pydantic import BaseModel, ConfigDict


class BaseContract(BaseModel):
    """全局统一契约基类，强制严格校验规则"""
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
        frozen=False
    )