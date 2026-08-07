"""Self-contained offline HTML renderer."""

from __future__ import annotations

from html import escape
from typing import Any

from .common import display_value


def render_html(result: dict[str, Any]) -> str:
    """Render a dependency-free dashboard that uses canonical result values."""
    metric_rows = "".join(
        "<tr><th>{}</th><td>{}</td></tr>".format(
            escape(key), escape(display_value(value, "%"))
        )
        for key, value in result["summary"]["metrics"].items()
    )
    evidence_items = "".join(
        "<li><strong>{}</strong> <span>{}</span><p>{}</p></li>".format(
            escape(item["evidence_id"]),
            escape(item["source_ref"]),
            escape(item["fact"]),
        )
        for item in result["evidence"]
    ) or "<li>No evidence was supplied.</li>"
    action_items = "".join(
        "<li><strong>{} / {} ({})</strong><p>{}</p><p>Retest: {}</p></li>".format(
            escape(action["actionId"]),
            escape(action["metricKey"]),
            escape(display_value(action["currentValue"], "%")),
            escape(action["suggestion"]),
            escape(action["retest"]),
        )
        for action in result["actions"]
    )
    mode = escape(result["analysisMode"])
    task_id = escape(result["taskId"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EvidenceClass report {task_id}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto;
      padding: 0 1rem; color: #172033; }}
    .boundary {{ background: #fff5d6; border-left: 4px solid #c27a00; padding: .8rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d8deea; padding: .6rem; text-align: left; }}
    li {{ margin-bottom: .8rem; }}
  </style>
</head>
<body>
  <h1>Classroom evidence analysis</h1>
  <p>Task <code>{task_id}</code> · mode <code>{mode}</code></p>
  <p class="boundary">Descriptive observations only. This output does not claim model
    accuracy or learning impact.</p>
  <h2>Summary metrics</h2>
  <table>{metric_rows}</table>
  <h2>Evidence</h2>
  <ol>{evidence_items}</ol>
  <h2>Actions and retest</h2>
  <ol>{action_items}</ol>
</body>
</html>
"""
