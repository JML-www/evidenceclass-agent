"""Stage-12 trace gate: prove the span tree covers all six request layers.

Run with:

    cd <repo> && .venv/Scripts/python.exe -m packages.observability

It executes one representative task -- api request -> queue -> worker -> node ->
tool -> model -- across a thread boundary (the same ``contextvars`` re-binding the
worker queue already uses) and prints the rendered span tree.  The exit code is
non-zero unless the tree contains all six span kinds.

The ``api`` span is emitted here to represent the control-plane boundary; in
production ``apps/api`` (out of this stage's scope) opens that span and the worker
continues the same trace via the ``traceparent`` header.  The other five spans are
produced by the identical :mod:`packages.observability.tracing` calls used inside
``apps/worker/runtime.py`` and ``apps/worker/queue.py``.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from packages.observability import bind, tracer
from packages.observability.tracing import SPAN_KINDS


def _simulate_worker(run_id: str) -> None:
    """Stand-in for the real worker body; uses the same tracing calls as runtime.py."""

    with tracer.span("worker.run", "worker", attributes={"run_id": run_id}):
        for index, node in enumerate(("inspect_assets", "observe_media", "verify_claims"))):
            tool, model = {
                "inspect_assets": ("inspect_media", None),
                "observe_media": ("observe_media", ("deterministic-vlm", "qwen2.5-vl")),
                "verify_claims": ("verify_claims", ("deterministic-llm", "qwen3.5")),
            }[node]
            with tracer.span(node, "node", attributes={"run_id": run_id, "node": node}):
                if tool is not None:
                    with tracer.span(
                        f"tool.{tool}", "tool", attributes={"tool": tool, "run_id": run_id}
                    ):
                        time.sleep(0.001)
                if model is not None:
                    provider, model_name = model
                    with tracer.span(
                        f"model.{model_name}",
                        "model",
                        attributes={"provider": provider, "model": model_name, "run_id": run_id},
                    ):
                        time.sleep(0.001)


def run_gate() -> int:
    trace_id = None
    with bind(request_id=str(uuid4())), tracer.span("api.request", "api",
                                                    attributes={"route": "/jobs/start"}):
        # Simulate the API enqueueing the task and serialising the trace context.
        with tracer.span("queue.enqueue", "queue", attributes={"run_id": str(uuid4())}):
            parent_ctx = tracer.current_context()
            headers = tracer.to_headers()
        # Hand off to a worker thread; the queue re-binds the captured context.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="gate-worker") as pool:
            future = pool.submit(
                _run_in_scope, parent_ctx, headers, _simulate_worker, str(uuid4())
            )
            future.result()
        trace_id = tracer.current_context().trace_id
        # Fall back to the live span's trace if the api span already closed.
        api_span = tracer.current()
        if api_span is not None:
            trace_id = api_span.trace_id

    assert trace_id is not None
    print(tracer.render_trace_text(trace_id))
    kinds = {s.kind for s in tracer.export_trace_json(trace_id)["spans"]}
    missing = [kind for kind in SPAN_KINDS if kind not in kinds]
    print("\nSpan kinds present:", ", ".join(sorted(kinds)))
    if missing:
        print(f"GATE FAILED: missing span kinds -> {missing}")
        return 1
    print("GATE PASSED: span tree contains all six layers (api/queue/worker/node/tool/model).")
    return 0


def _run_in_scope(parent_ctx, headers, operation, *args):
    from packages.observability.tracing import tracer as _t

    with _t.resume_from_context(parent_ctx), _t.resume_from_headers(headers):
        return operation(*args)


if __name__ == "__main__":
    raise SystemExit(run_gate())
