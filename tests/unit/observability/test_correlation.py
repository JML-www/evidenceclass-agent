from __future__ import annotations

from uuid import UUID

from packages.observability import CorrelationContext, bind, current


def test_new_context_generates_a_request_id_and_ignores_unknown_fields():
    context = CorrelationContext.new(workspace_id="ws-1", unknown_field="ignored")
    UUID(context.request_id)  # must be a real uuid
    assert context.workspace_id == "ws-1"
    assert not hasattr(context, "unknown_field")


def test_headers_round_trip_through_every_correlation_field():
    context = CorrelationContext.new(
        workspace_id="ws-1",
        job_id="job-1",
        run_id="run-1",
        step_id="step-1",
        tool_call_id="tool-1",
        model_call_id="model-1",
    )
    restored = CorrelationContext.from_headers(context.to_headers())
    assert restored == context


def test_from_headers_is_case_insensitive_and_generates_when_absent():
    restored = CorrelationContext.from_headers({"x-request-id": "req-9", "X-Workspace-ID": "ws-9"})
    assert restored.request_id == "req-9"
    assert restored.workspace_id == "ws-9"
    assert UUID(CorrelationContext.from_headers(None).request_id)


def test_bind_inherits_and_narrows_the_scope_then_restores_it():
    outer = CorrelationContext.new(request_id="req-1", job_id="job-1")
    assert current() is None
    with bind(outer) as bound:
        assert bound.request_id == "req-1"
        with bind(run_id="run-1") as child:
            assert child.request_id == "req-1"
            assert child.run_id == "run-1"
            assert child.step_id is None
        assert current() is not None
        assert current().run_id is None
    assert current() is None


def test_derive_and_as_labels_only_expose_known_fields():
    context = CorrelationContext.new(workspace_id="ws", job_id="job")
    labels = context.derive(run_id="run").as_labels()
    assert set(labels) == {"request_id", "workspace_id", "job_id", "run_id"}


def test_request_id_is_required_to_open_a_scope():
    try:
        CorrelationContext(request_id="")
    except ValueError as exc:
        assert "request_id" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("an empty request_id must be rejected")
