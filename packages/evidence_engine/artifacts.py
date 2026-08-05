"""Artifact-boundary helpers retained by the characterization suite."""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {
    "face_embedding",
    "faceembedding",
    "facial_feature",
    "facialfeature",
    "local_path",
    "localpath",
    "seat_identity",
    "seatidentity",
    "student_id",
    "student_name",
    "student_no",
    "studentid",
    "studentname",
    "studentno",
}


def anonymize(value: Any) -> Any:
    """Return a recursive copy without known direct-identifier fields."""
    if isinstance(value, dict):
        return {
            key: anonymize(item) for key, item in value.items() if key.lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [anonymize(item) for item in value]
    return value
