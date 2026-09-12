"""Lightweight in-process metrics registry with Prometheus text exposition.

The registry is dependency-free so it works in the offline CI environment and in
the single-process acceptance runs.  Counters, gauges and histograms share one
namespace; ``snapshot()`` returns plain data for assertions and ``render()``
produces the Prometheus text format consumed by a scraper or a local dashboard.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

DEFAULT_BUCKETS: tuple[float, ...] = (
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1_000.0,
    2_500.0,
    5_000.0,
    10_000.0,
    30_000.0,
    60_000.0,
)

_NAME_SANITIZER = re.compile(r"[^a-zA-Z0-9_:]")


def _metric_name(name: str) -> str:
    cleaned = _NAME_SANITIZER.sub("_", name.strip())
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"evidenceclass_{cleaned}"
    return cleaned


def _label_key(labels: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{name}="{_escape(value)}"' for name, value in labels)
    return f"{{{inner}}}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@dataclass
class _HistogramState:
    buckets: tuple[float, ...]
    counts: dict[tuple[tuple[str, str], ...], list[int]] = field(default_factory=dict)
    totals: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)
    observations: dict[tuple[tuple[str, str], ...], int] = field(default_factory=dict)


class MetricsRegistry:
    """Thread-safe counters, gauges and histograms."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
        self._histograms: dict[str, _HistogramState] = {}
        self._help: dict[str, str] = {}

    # -- write -------------------------------------------------------------
    def increment(
        self, name: str, amount: float = 1.0, *, labels: Mapping[str, Any] | None = None,
        help: str | None = None,
    ) -> None:
        metric = _metric_name(name)
        key = _label_key(labels)
        with self._lock:
            if help:
                self._help.setdefault(metric, help)
            bucket = self._counters.setdefault(metric, {})
            bucket[key] = bucket.get(key, 0.0) + float(amount)

    def set_gauge(
        self, name: str, value: float, *, labels: Mapping[str, Any] | None = None,
        help: str | None = None,
    ) -> None:
        metric = _metric_name(name)
        key = _label_key(labels)
        with self._lock:
            if help:
                self._help.setdefault(metric, help)
            self._gauges.setdefault(metric, {})[key] = float(value)

    def add_gauge(
        self, name: str, delta: float, *, labels: Mapping[str, Any] | None = None,
        help: str | None = None,
    ) -> None:
        metric = _metric_name(name)
        key = _label_key(labels)
        with self._lock:
            if help:
                self._help.setdefault(metric, help)
            bucket = self._gauges.setdefault(metric, {})
            bucket[key] = bucket.get(key, 0.0) + float(delta)

    def observe(
        self, name: str, value: float, *, labels: Mapping[str, Any] | None = None,
        help: str | None = None, buckets: Iterable[float] | None = None,
    ) -> None:
        metric = _metric_name(name)
        key = _label_key(labels)
        bound = tuple(sorted(float(b) for b in (buckets or DEFAULT_BUCKETS)))
        numeric = float(value)
        with self._lock:
            if help:
                self._help.setdefault(metric, help)
            state = self._histograms.get(metric)
            if state is None:
                state = _HistogramState(buckets=bound)
                self._histograms[metric] = state
            slots = state.counts.setdefault(key, [0] * len(state.buckets))
            for index, upper in enumerate(state.buckets):
                if numeric <= upper:
                    slots[index] += 1
            state.totals[key] = state.totals.get(key, 0.0) + numeric
            state.observations[key] = state.observations.get(key, 0) + 1

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._help.clear()

    # -- read --------------------------------------------------------------
    def counter_value(self, name: str, *, labels: Mapping[str, Any] | None = None) -> float:
        return self._counters.get(_metric_name(name), {}).get(_label_key(labels), 0.0)

    def gauge_value(self, name: str, *, labels: Mapping[str, Any] | None = None) -> float | None:
        return self._gauges.get(_metric_name(name), {}).get(_label_key(labels))

    def histogram_summary(
        self, name: str, *, labels: Mapping[str, Any] | None = None
    ) -> dict[str, float | int]:
        """Summarize a histogram for one label set, or across every label set.

        Passing ``labels=None`` aggregates all series, which is what the
        operations panel wants when it shows a single per-stage number.
        """

        state = self._histograms.get(_metric_name(name))
        if state is None:
            return {"count": 0, "sum": 0.0, "avg": 0.0}
        if labels is None:
            count = sum(state.observations.values())
            total = sum(state.totals.values())
        else:
            key = _label_key(labels)
            count = state.observations.get(key, 0)
            total = state.totals.get(key, 0.0)
        return {
            "count": count,
            "sum": round(total, 3),
            "avg": round(total / count, 3) if count else 0.0,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {
                    name: {"|".join(f"{k}={v}" for k, v in key) or "_": value}
                    for name, bucket in self._counters.items()
                    for key, value in bucket.items()
                },
                "gauges": {
                    name: {"|".join(f"{k}={v}" for k, v in key) or "_": value}
                    for name, bucket in self._gauges.items()
                    for key, value in bucket.items()
                },
                "histograms": {
                    name: {
                        "count": sum(state.observations.values()),
                        "sum": round(sum(state.totals.values()), 3),
                        "buckets": list(state.buckets),
                    }
                    for name, state in self._histograms.items()
                },
            }

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, bucket in sorted(self._counters.items()):
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} counter")
                for key, value in sorted(bucket.items()):
                    lines.append(f"{name}{_render_labels(key)} {_format(value)}")
            for name, bucket in sorted(self._gauges.items()):
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} gauge")
                for key, value in sorted(bucket.items()):
                    lines.append(f"{name}{_render_labels(key)} {_format(value)}")
            for name, state in sorted(self._histograms.items()):
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} histogram")
                for key, slots in sorted(state.counts.items()):
                    # ``slots[i]`` already counts every observation <= buckets[i],
                    # so the histogram buckets are cumulative by construction.
                    for upper, count in zip(state.buckets, slots, strict=True):
                        label_key = key + (("le", _format(upper)),)
                        lines.append(f"{name}_bucket{_render_labels(label_key)} {count}")
                    label_key = key + (("le", "+Inf"),)
                    total = state.observations.get(key, 0)
                    lines.append(f"{name}_bucket{_render_labels(label_key)} {total}")
                    total_value = _format(state.totals.get(key, 0.0))
                    lines.append(f"{name}_sum{_render_labels(key)} {total_value}")
                    lines.append(f"{name}_count{_render_labels(key)} {total}")
        return "\n".join(lines) + "\n"


def _format(value: float) -> str:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "+Inf" if value > 0 else "-Inf"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}"


#: Process-wide default registry used by the API, worker and instrumentation.
METRICS = MetricsRegistry()


def metrics() -> MetricsRegistry:
    return METRICS
