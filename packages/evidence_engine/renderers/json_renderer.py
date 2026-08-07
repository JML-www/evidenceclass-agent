"""Canonical JSON renderer."""

from __future__ import annotations

import json
from typing import Any


def render_json(result: dict[str, Any]) -> str:
    """Serialize the already-built semantic result with stable key ordering."""
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
