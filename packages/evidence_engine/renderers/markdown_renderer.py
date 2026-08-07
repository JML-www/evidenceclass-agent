"""Plain Markdown report renderer."""

from __future__ import annotations

from typing import Any

from .common import display_value


def render_markdown(result: dict[str, Any]) -> str:
    """Render a readable report from canonical values only."""
    lines = [
        "# Classroom evidence analysis report",
        "",
        f"- Task: `{result['taskId']}`",
        f"- Analysis mode: `{result['analysisMode']}`",
        "- Measurement boundary: descriptive observations; no accuracy claim",
        "",
        "## Summary metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in result["summary"]["metrics"].items():
        lines.append(f"| {key} | {display_value(value, '%')} |")
    lines.extend(
        [
            "",
            f"Overall: {display_value(result['summary']['overall'])}",
            "",
            "## Evidence",
            "",
        ]
    )
    if result["evidence"]:
        for item in result["evidence"]:
            lines.append(f"- **{item['evidence_id']}** ({item['source_ref']}): {item['fact']}")
    else:
        lines.append("- No evidence was supplied.")
    lines.extend(["", "## Actions and retest", ""])
    for action in result["actions"]:
        current = display_value(action["currentValue"], "%")
        lines.append(
            f"- **{action['actionId']} / {action['metricKey']} ({current})**: "
            f"{action['suggestion']} Retest: {action['retest']}"
        )
    return "\n".join(lines) + "\n"
