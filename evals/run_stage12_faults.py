"""Run the stage-12 fault-injection harness and publish the incident report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.observability import metrics as metrics_registry
from packages.observability.faults import FAULT_IDS, render_markdown, run_all

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the stage-12 fault injections.")
    parser.add_argument(
        "--report",
        default=str(ROOT / "docs" / "incidents" / "fault-injection-001.md"),
        help="Markdown incident report to publish",
    )
    parser.add_argument(
        "--json",
        default=str(ROOT / "runs" / "stage-12" / "fault-injection-001.json"),
        help="Machine-readable outcome dump (gitignored runs/ by default)",
    )
    args = parser.parse_args(argv)

    registry = metrics_registry()
    outcomes = run_all(registry=registry)
    expected = set(FAULT_IDS)
    observed = {item.fault_id for item in outcomes}
    missing = sorted(expected - observed)
    unrecovered = [item.fault_id for item in outcomes if not item.recovered]

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(outcomes), encoding="utf-8")

    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "scenarios": [item.as_dict() for item in outcomes],
                "missing": missing,
                "unrecovered": unrecovered,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenarios": len(outcomes),
                "unrecovered": unrecovered,
                "missing": missing,
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not missing and not unrecovered else 1


if __name__ == "__main__":
    raise SystemExit(main())
