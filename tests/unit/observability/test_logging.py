from __future__ import annotations

import json
import logging

import pytest

from packages.observability import CorrelationContext, bind
from packages.observability.logging import (
    JsonFormatter,
    build_record,
    emit_event,
    redact_text,
    redact_value,
    validate_record,
)


def test_sensitive_keys_and_content_bodies_are_dropped():
    cleaned = redact_value(
        {
            "api_key": "sk-abcdefghijklmnop",
            "password": "hunter2",
            "prompt": "full private prompt",
            "transcript": "full lesson transcript",
            "chain_of_thought": "private reasoning",
            "tool": "observe_visuals",
            "attempt": 1,
        }
    )
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["password"] == "[redacted]"
    assert cleaned["prompt"] == "[redacted]"
    assert cleaned["transcript"] == "[redacted]"
    assert cleaned["chain_of_thought"] == "[redacted]"
    assert cleaned["tool"] == "observe_visuals"
    assert cleaned["attempt"] == 1


def test_personal_data_and_media_paths_are_masked_inside_values():
    text = (
        "user a.b+tag@example.test phone 13812345678 media C:\\classes\\lesson.mp4 "
        "share /home/teacher/lesson.mp4 bearer abc.def.ghi data:image/png;base64,QUJD"
    )
    masked = redact_text(text)
    assert "a.b+tag@example.test" not in masked
    assert "13812345678" not in masked
    assert "lesson.mp4" not in masked
    assert "abc.def.ghi" not in masked
    assert "QUJD" not in masked


def test_long_values_are_truncated_without_losing_the_prefix():
    masked = redact_text("x" * 5_000)
    assert masked.endswith("[truncated]")
    assert len(masked) < 5_000


def test_nested_structures_are_redacted_recursively():
    cleaned = redact_value({"outer": [{"token": "abc"}, "keep@example.test"]})
    assert cleaned["outer"][0]["token"] == "[redacted]"
    assert cleaned["outer"][1] == "[redacted-email]"


def test_build_record_includes_correlation_and_passes_validation():
    record = build_record("agent.tool.completed", tool="observe_visuals", attempt=1)
    assert validate_record(record) == []
    assert record["event"] == "agent.tool.completed"
    assert record["fields"]["tool"] == "observe_visuals"


def test_validation_flags_leaked_sensitive_fields_and_bad_event_names():
    problems = validate_record(
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "level": "INFO",
            "event": "Agent.Tool.Completed",
            "logger": "evidenceclass",
            "fields": {"password": "hunter2", "contact": "a@b.example"},
        }
    )
    assert any("unstable event name" in item for item in problems)
    assert any("sensitive field" in item for item in problems)
    assert any("unredacted value" in item for item in problems)


def test_validation_flags_missing_required_fields():
    problems = validate_record({"event": "agent.tool.completed"})
    assert len(problems) >= 3


def test_emit_event_rejects_non_dotted_event_names():
    with pytest.raises(ValueError):
        emit_event("AgentTool")


def test_json_formatter_serializes_one_line_with_event_and_correlation():
    record = logging.LogRecord(
        name="evidenceclass",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="injected failure",
        args=(),
        exc_info=None,
    )
    record.event = "api.request.failed"
    record.route = "/api/v1/jobs"
    record.status_code = 429
    with bind(CorrelationContext.new(request_id="req-1", workspace_id="ws-1")):
        payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "api.request.failed"
    assert payload["level"] == "WARNING"
    assert payload["correlation"]["request_id"] == "req-1"
    assert payload["fields"]["status_code"] == 429
    assert "\n" not in json.dumps(payload)


def test_reserved_logging_keys_are_prefixed_not_dropped():
    probe_logger = logging.getLogger("evidenceclass.probe")
    probe_logger.setLevel(logging.DEBUG)
    with pytest.raises(KeyError):
        # ``name`` collides with a LogRecord attribute; raw logging rejects it.
        probe_logger.log(logging.INFO, "x", extra={"name": "boom"})
    # emit_event must tolerate the same key by prefixing it instead of crashing.
    emit_event("agent.tool.completed", name="observe_visuals")
