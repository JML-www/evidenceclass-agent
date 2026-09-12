"""Local asynchronous queue used for deterministic development and acceptance."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar
from uuid import UUID, uuid4

from packages.observability import CorrelationContext, bind, current
from packages.observability.tracing import tracer

from .runtime import RuntimeWorker

T = TypeVar("T")


def run_with_correlation(
    context: CorrelationContext | None,
    trace_context: "SpanContext | None",
    operation: Callable[..., T],
    *args: Any,
) -> T:
    """Run ``operation`` with the caller's correlation and span scope re-bound.

    ``ThreadPoolExecutor`` does not copy ``contextvars`` into the worker thread,
    so both the correlation scope and the active span context are captured on the
    producing thread and re-bound inside the worker thread.  This keeps the span
    tree continuous across the queue boundary.
    """

    with bind(context), tracer.resume_from_context(trace_context):
        return operation(*args)


class InProcessTaskQueue:
    def __init__(
        self, worker: RuntimeWorker, *, auto_run: bool = True, max_workers: int = 2
    ) -> None:
        self.worker = worker
        self.auto_run = auto_run
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="evidenceclass-worker"
        )
        self._futures: dict[str, Future] = {}

    def enqueue(self, run_id: UUID) -> str:
        task_id = str(uuid4())
        if self.auto_run and self.worker is not None:
            trace_ctx = tracer.current_context()
            with tracer.span("queue.enqueue", "queue", attributes={"run_id": str(run_id)}):
                self._futures[task_id] = self._executor.submit(
                    run_with_correlation, current(), trace_ctx, self.worker.run, run_id
                )
        return task_id

    def enqueue_resume(self, run_id: UUID, decision: str) -> str:
        task_id = str(uuid4())
        if self.auto_run and self.worker is not None:
            trace_ctx = tracer.current_context()
            with tracer.span("queue.enqueue_resume", "queue", attributes={"run_id": str(run_id)}):
                self._futures[task_id] = self._executor.submit(
                    run_with_correlation, current(), trace_ctx, self.worker.resume, run_id, decision
                )
        return task_id

    def run_now(self, run_id: UUID) -> dict[str, object]:
        trace_ctx = tracer.current_context()
        with tracer.span("queue.enqueue", "queue", attributes={"run_id": str(run_id)}):
            return run_with_correlation(current(), trace_ctx, self.worker.run, run_id)

    def cancel(self, task_id: str) -> bool:
        future = self._futures.get(task_id)
        return future.cancel() if future is not None else False

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class CeleryTaskQueue:
    """Thin producer adapter; worker processes execute the named Celery task.

    Correlation identifiers ride along as task headers so a single API request
    can be joined to the worker, agent node, tool and model-call spans.
    """

    def enqueue(self, run_id: UUID) -> str:
        from .celery_app import run_agent

        return str(run_agent.apply_async(args=[str(run_id)], headers=_headers()).id)

    def enqueue_resume(self, run_id: UUID, decision: str) -> str:
        from .celery_app import resume_agent

        return str(
            resume_agent.apply_async(args=[str(run_id), decision], headers=_headers()).id
        )

    def cancel(self, task_id: str) -> bool:
        from .celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=True)
        return True


def _headers() -> dict[str, str] | None:
    scope = current()
    headers = scope.to_headers() if scope is not None else {}
    headers.update(tracer.to_headers())
    return headers or None
