"""Structured JSON logging with stable event names and mandatory redaction.

Logs are machine-searchable: every record emits a stable ``event`` name plus the
correlation identifiers from :mod:`packages.observability.correlation`.  Secrets,
raw media, full transcripts, model chain-of-thought and unmasked personal data
are removed before a record is serialized.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .correlation import CORRELATION_FIELDS
from .correlation import current as current_correlation

#: ``agent.tool.completed`` style: lower snake segments joined by dots.
EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")

RESERVED_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

#: Keys whose value is dropped entirely: credentials, prompts, media, transcripts.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(secret|token|password|passwd|authorization|api[_-]?key|credential|signature"
    r"|private[_-]?key|session[_-]?id|cookie)",
    re.IGNORECASE,
)
BLOCKED_CONTENT_KEYS = frozenset(
    {
        "prompt",
        "prompts",
        "system_prompt",
        "messages",
        "transcript",
        "full_transcript",
        "chain_of_thought",
        "chain_of_thought_text",
        "reasoning",
        "reasoning_text",
        "cot",
        "raw_media",
        "media_bytes",
        "audio_bytes",
        "image_bytes",
        "video_bytes",
        "file_bytes",
        "raw_response",
    }
)

_VALUE_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"data:[^\s,;]+;base64,[A-Za-z0-9+/=]+"), "[redacted-data-uri]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer [redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"), "[redacted-secret]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[redacted-email]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[redacted-phone]"),
    (re.compile(r"[A-Za-z]:\\[^\s\"']+"), "[redacted-path]"),
    (
        re.compile(r"(?<![\w:/])/(?:home|Users|var|tmp|mnt|data|storage)/[^\s\"']+"),
        "[redacted-path]",
    ),
)

MAX_STRING_LENGTH = 512
REDACTED = "[redacted]"

_LOGGER_NAME = "evidenceclass"


def redact_value(value: Any, *, depth: int = 0) -> Any:
    """Recursively drop secrets and mask personal or media-bearing strings."""

    if depth > 6:
        return "[truncated-depth]"
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if SENSITIVE_KEY_PATTERN.search(name) or name.casefold() in BLOCKED_CONTENT_KEYS:
                cleaned[name] = REDACTED
            else:
                cleaned[name] = redact_value(item, depth=depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_value(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_text(str(value))


def redact_text(text: str) -> str:
    for pattern, replacement in _VALUE_REDACTIONS:
        text = pattern.sub(replacement, text)
    if len(text) > MAX_STRING_LENGTH:
        return f"{text[:MAX_STRING_LENGTH]}...[truncated]"
    return text


def _correlation_fields() -> dict[str, str]:
    scope = current_correlation()
    if scope is None:
        return {}
    return {name: str(value) for name, value in scope.as_dict().items() if value is not None}


def build_record(
    event: str,
    *,
    level: str = "INFO",
    logger: str = _LOGGER_NAME,
    message: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build a canonical log record, applying redaction and correlation lookup."""

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "logger": logger,
    }
    if message is not None:
        record["message"] = redact_text(message)
    correlation = _correlation_fields()
    if correlation:
        record["correlation"] = correlation
        for name in CORRELATION_FIELDS:
            if name in correlation:
                record[name] = correlation[name]
    if fields:
        record["fields"] = redact_value(fields)
    return record


class JsonFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if not event:
            event = "log.message"
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "event": event,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        correlation = _correlation_fields()
        if correlation:
            payload["correlation"] = correlation
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in RESERVED_RECORD_KEYS and key not in {"event", "exc_info"}
        }
        if extras:
            payload["fields"] = redact_value(extras)
        if record.exc_info:
            payload["error"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or _LOGGER_NAME)


def emit_event(
    event: str,
    *,
    level: int = logging.INFO,
    logger: str | None = None,
    message: str | None = None,
    **fields: Any,
) -> None:
    """Emit one structured record under a stable event name.

    Fields are attached through ``extra=``; any name that would collide with a
    reserved :class:`logging.LogRecord` attribute is prefixed with ``field_``.
    """

    if not EVENT_NAME_PATTERN.match(event):
        raise ValueError(f"event name must be dotted lower_snake_case: {event!r}")
    extra: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        extra[key if key not in RESERVED_RECORD_KEYS else f"field_{key}"] = value
    get_logger(logger).log(level, message or event, extra=extra)


def configure_logging(level: int = logging.INFO, stream: Any | None = None) -> logging.Logger:
    """Install the JSON formatter on the project logger (idempotent)."""

    logger = get_logger()
    logger.setLevel(level)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.propagate = False
    return logger


def _leaked_sensitive_keys(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 6 or not isinstance(value, Mapping):
        return []
    leaked: list[str] = []
    for key, item in value.items():
        name = str(key)
        is_sensitive = SENSITIVE_KEY_PATTERN.search(name) or name.casefold() in BLOCKED_CONTENT_KEYS
        if is_sensitive and item != REDACTED:
            leaked.append(name)
        leaked.extend(_leaked_sensitive_keys(item, depth=depth + 1))
    return leaked


def validate_record(record: Mapping[str, Any]) -> list[str]:
    """Return the list of schema/redaction violations for a log record.

    Used by tests and by the acceptance gate to prove that the logging pipeline
    both keeps its contract (stable event names, required fields) and never
    persists secrets, personal data or media paths.
    """

    problems: list[str] = []
    for required in ("timestamp", "level", "event", "logger"):
        if not record.get(required):
            problems.append(f"missing required field: {required}")
    event = str(record.get("event", ""))
    if event and not EVENT_NAME_PATTERN.match(event):
        problems.append(f"unstable event name: {event!r}")
    for key in _leaked_sensitive_keys(record):
        problems.append(f"sensitive field was not redacted: {key}")
    serialized = json.dumps(record, ensure_ascii=False, default=str)
    for pattern, _ in _VALUE_REDACTIONS:
        if pattern.search(serialized):
            problems.append(f"unredacted value matched pattern: {pattern.pattern}")
    return problems
