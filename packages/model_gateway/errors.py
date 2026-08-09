"""Stable error taxonomy that is independent of any provider SDK."""

from __future__ import annotations


class ModelGatewayError(RuntimeError):
    error_code = "MODEL_GATEWAY_ERROR"
    retryable = False
    repairable = False

    def __init__(self, message: str, *, raw_response_ref: str | None = None) -> None:
        super().__init__(message)
        self.raw_response_ref = raw_response_ref


class ModelTimeoutError(ModelGatewayError):
    error_code = "MODEL_TIMEOUT"
    retryable = True


class ModelRateLimitError(ModelGatewayError):
    error_code = "MODEL_RATE_LIMITED"
    retryable = True


class ModelServerError(ModelGatewayError):
    error_code = "MODEL_SERVER_ERROR"
    retryable = True


class SchemaParseError(ModelGatewayError):
    error_code = "MODEL_SCHEMA_PARSE_FAILED"
    repairable = True


class SemanticValidationError(ModelGatewayError):
    error_code = "MODEL_SEMANTIC_VALIDATION_FAILED"


class CapabilityUnavailableError(ModelGatewayError):
    error_code = "MODEL_CAPABILITY_UNAVAILABLE"


class ModelAuthenticationError(ModelGatewayError):
    error_code = "MODEL_AUTHENTICATION_FAILED"


class ModelPermissionDeniedError(ModelGatewayError):
    error_code = "MODEL_PERMISSION_DENIED"


class ModelContentPolicyError(ModelGatewayError):
    error_code = "MODEL_CONTENT_POLICY_BLOCKED"


class DeterministicModelRequestError(ModelGatewayError):
    error_code = "MODEL_REQUEST_INVALID"


class ModelBudgetExceededError(ModelGatewayError):
    error_code = "MODEL_BUDGET_EXCEEDED"
    resolution = "NEEDS_REVIEW"


class CircuitOpenError(ModelGatewayError):
    error_code = "MODEL_CIRCUIT_OPEN"


class LocalRateLimitError(ModelGatewayError):
    error_code = "MODEL_LOCAL_RATE_LIMIT"
    retryable = True


class UnknownCostError(ModelGatewayError):
    error_code = "MODEL_COST_UNKNOWN"
