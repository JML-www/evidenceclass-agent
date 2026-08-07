"""Shared presentation-only helpers."""

from __future__ import annotations

from typing import Any


def display_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"
