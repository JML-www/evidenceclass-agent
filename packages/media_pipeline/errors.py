"""Stable, user-safe failures raised by the phase-5 media boundary."""

from __future__ import annotations


class MediaPipelineError(RuntimeError):
    """Base error with a stable code suitable for Job failure/review routing."""

    code = "MEDIA_PIPELINE_ERROR"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class MediaToolUnavailableError(MediaPipelineError):
    code = "MEDIA_TOOL_UNAVAILABLE"


class UnsafeMediaPathError(MediaPipelineError):
    code = "UNSAFE_MEDIA_PATH"


class UnsupportedMediaError(MediaPipelineError):
    code = "UNSUPPORTED_MEDIA"


class CorruptMediaError(MediaPipelineError):
    code = "CORRUPT_MEDIA"


class MediaLimitExceededError(MediaPipelineError):
    code = "MEDIA_LIMIT_EXCEEDED"


class MediaToolExecutionError(MediaPipelineError):
    code = "MEDIA_TOOL_EXECUTION_FAILED"


class MediaManifestError(MediaPipelineError):
    code = "MEDIA_MANIFEST_INVALID"
