"""Observability, reliability and performance primitives for EvidenceClass Agent.

This package is the single home for cross-cutting concerns introduced in stage 12:

- :mod:`packages.observability.correlation` — the seven unified correlation ids
- :mod:`packages.observability.logging` — structured JSON logs with redaction
- :mod:`packages.observability.metrics` — counters, gauges and histograms
- :mod:`packages.observability.timing` — per-run stage timeline and memory sampling
- :mod:`packages.observability.reliability` — stable infrastructure failure classification
- :mod:`packages.observability.faults` — the deterministic fault-injection harness
"""

from .correlation import (
    CORRELATION_FIELDS,
    HEADER_NAMES,
    CorrelationContext,
    bind,
    current,
    require_current,
)
from .logging import (
    JsonFormatter,
    configure_logging,
    emit_event,
    get_logger,
    redact_value,
    validate_record,
)
from .metrics import MetricsRegistry, metrics
from .reliability import ReliabilityVerdict, classify_infrastructure_error
from .timing import STAGE_NAMES, StageTimeline, peak_memory_mb

__all__ = [
    "CORRELATION_FIELDS",
    "HEADER_NAMES",
    "STAGE_NAMES",
    "CorrelationContext",
    "JsonFormatter",
    "MetricsRegistry",
    "ReliabilityVerdict",
    "StageTimeline",
    "bind",
    "classify_infrastructure_error",
    "configure_logging",
    "current",
    "emit_event",
    "get_logger",
    "metrics",
    "peak_memory_mb",
    "redact_value",
    "require_current",
    "validate_record",
]
