"""Stable classification of infrastructure failures for API and worker callers.

A fault must degrade in a *predictable* way: retry, apply backpressure, degrade
the capability, or fail closed.  This module keeps that decision in one place so
the API, the queue guard and the fault-injection report agree on the outcome.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from packages.model_gateway.errors import ModelGatewayError

RETRY = "RETRY"
BACKPRESSURE = "BACKPRESSURE"
DEGRADE = "DEGRADE"
FAIL = "FAIL"
NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class ReliabilityVerdict:
    code: str
    retryable: bool
    resolution: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_DB_EXHAUSTION_HINTS = (
    "too many clients",
    "connection pool",
    "remaining connection slots",
    "max_connections",
    "pool timed out",
    "connection refused",
    "server closed the connection",
)


def classify_infrastructure_error(exc: BaseException) -> ReliabilityVerdict:
    """Map a raised exception to a stable reliability verdict."""

    if isinstance(exc, ModelGatewayError):
        resolution = getattr(exc, "resolution", None)
        if resolution:
            return ReliabilityVerdict(
                code=exc.error_code,
                retryable=exc.retryable,
                resolution=str(resolution),
                reason="gateway-provided resolution",
            )
        return ReliabilityVerdict(
            code=exc.error_code,
            retryable=exc.retryable,
            resolution=RETRY if exc.retryable else FAIL,
            reason="gateway error taxonomy",
        )

    name = type(exc).__name__

    if name == "WorkerInterrupted":
        return ReliabilityVerdict(
            code="WORKER_INTERRUPTED",
            retryable=True,
            resolution=RETRY,
            reason="checkpoint exists; the run can resume from the last successful node",
        )

    if isinstance(exc, SqlAlchemyTimeoutError):
        return ReliabilityVerdict(
            code="DB_CONNECTION_EXHAUSTED",
            retryable=True,
            resolution=BACKPRESSURE,
            reason="connection checkout timed out; shed load before retrying",
        )

    if isinstance(exc, (OperationalError, DBAPIError)):
        message = str(getattr(exc, "orig", exc)).casefold()
        exhausted = any(hint in message for hint in _DB_EXHAUSTION_HINTS)
        return ReliabilityVerdict(
            code="DB_CONNECTION_EXHAUSTED" if exhausted else "DB_OPERATIONAL_ERROR",
            retryable=exhausted,
            resolution=BACKPRESSURE if exhausted else FAIL,
            reason="database refused or dropped the connection",
        )

    if isinstance(exc, subprocess.TimeoutExpired):
        return ReliabilityVerdict(
            code="SUBPROCESS_STUCK",
            retryable=False,
            resolution=DEGRADE,
            reason="media subprocess exceeded its budget; kill and degrade, never loop",
        )

    if isinstance(exc, (ConnectionError, OSError)):
        return ReliabilityVerdict(
            code="BROKER_UNAVAILABLE",
            retryable=True,
            resolution=BACKPRESSURE,
            reason="broker or network dependency is unreachable",
        )

    return ReliabilityVerdict(
        code="UNCLASSIFIED_INFRASTRUCTURE_ERROR",
        retryable=False,
        resolution=FAIL,
        reason="no retry policy is defined; fail closed",
    )
