"""Evidence-ledger and action-plan CSV renderers."""

from __future__ import annotations

import csv
import io
from typing import Any


def _csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def render_evidence_csv(result: dict[str, Any]) -> str:
    """Render evidence provenance exactly as stored in the semantic result."""
    rows = []
    for item in result["evidence"]:
        rows.append(
            [
                item["evidence_id"],
                item["source_type"],
                item["source_ref"],
                item["timestamp_start_sec"],
                item["timestamp_end_sec"],
                item["fact"],
                item["confidence"],
                " | ".join(item["limitations"]),
            ]
        )
    return _csv_text(
        [
            "evidence_id",
            "source_type",
            "source_ref",
            "timestamp_start_sec",
            "timestamp_end_sec",
            "fact",
            "confidence",
            "limitations",
        ],
        rows,
    )


def render_actions_csv(result: dict[str, Any]) -> str:
    """Render evidence-linked suggestions and their source metric value."""
    rows = []
    for action in result["actions"]:
        rows.append(
            [
                action["actionId"],
                action["metricKey"],
                action["currentValue"],
                action["suggestion"],
                action["retest"],
                " | ".join(action["evidenceIds"]),
            ]
        )
    return _csv_text(
        [
            "action_id",
            "metric_key",
            "current_value",
            "suggestion",
            "retest",
            "evidence_ids",
        ],
        rows,
    )
