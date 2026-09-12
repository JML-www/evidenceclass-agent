"""Per-run stage timeline shared by worker instrumentation and the benchmark.

The stage names mirror the fields required by the performance baseline so that a
single short-video run can be rendered into the operations panel without any
post-processing.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar

from .metrics import MetricsRegistry
from .metrics import metrics as default_metrics

STAGE_NAMES: tuple[str, ...] = (
    "upload_ms",
    "queue_wait_ms",
    "probe_ms",
    "frame_extract_ms",
    "asr_ms",
    "ocr_ms",
    "vlm_ms",
    "retrieval_ms",
    "agent_overhead_ms",
    "artifact_ms",
    "end_to_end_ms",
)

T = TypeVar("T")


def peak_memory_mb() -> float | None:
    """Best-effort resident-memory high-water mark in megabytes.

    ``resource`` is unavailable on Windows, so the sampler degrades to a
    ``tracemalloc`` peak when tracing is enabled and to ``None`` otherwise.
    A missing value is reported as unknown rather than guessed.
    """

    try:  # pragma: no cover - platform dependent
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kilobytes, macOS reports bytes.
        divisor = 1024.0 if usage < 1_000_000_000 else 1024.0 * 1024.0
        return round(usage / divisor, 3)
    except ImportError:
        pass
    try:
        import tracemalloc

        if not tracemalloc.is_tracing():
            return None
        _current, peak = tracemalloc.get_traced_memory()
        return round(peak / (1024.0 * 1024.0), 3)
    except Exception:  # noqa: BLE001 - sampling must never break a run
        return None


class StageTimeline:
    """Accumulates millisecond durations per stage for one run."""

    def __init__(self, *, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._started = clock()
        self._stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if name not in STAGE_NAMES:
            raise ValueError(f"unknown stage: {name!r}")
        started = self._clock()
        try:
            yield
        finally:
            self.record(name, (self._clock() - started) * 1000.0)

    def measure(self, name: str, operation: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        with self.stage(name):
            return operation(*args, **kwargs)

    def record(self, name: str, duration_ms: float) -> None:
        if name not in STAGE_NAMES:
            raise ValueError(f"unknown stage: {name!r}")
        if duration_ms < 0:
            raise ValueError("stage duration cannot be negative")
        self._stages[name] = round(self._stages.get(name, 0.0) + duration_ms, 3)

    def stages(self) -> dict[str, float]:
        return dict(self._stages)

    def finalize(self) -> dict[str, float]:
        elapsed = (self._clock() - self._started) * 1000.0
        previous = self._stages.get("end_to_end_ms", 0.0)
        self._stages["end_to_end_ms"] = round(max(previous, elapsed), 3)
        return self.stages()

    def with_memory(self) -> dict[str, float | None]:
        data: dict[str, float | None] = self.finalize()
        data["peak_memory_mb"] = peak_memory_mb()
        return data

    def publish(
        self,
        *,
        registry: MetricsRegistry | None = None,
        labels: Mapping[str, Any] | None = None,
        prefix: str = "evidenceclass_stage",
    ) -> None:
        target = registry or default_metrics()
        for name, value in self.finalize().items():
            target.observe(
                f"{prefix}_{name.replace('_ms', '')}_milliseconds",
                value,
                labels=labels,
                help="Per-stage duration of one analysis run",
            )
