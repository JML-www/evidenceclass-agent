"""Command-line interface for the standalone deterministic engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .service import EngineInputError, EvidenceEngineService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidenceclass")
    commands = parser.add_subparsers(dest="command", required=True)
    engine = commands.add_parser("engine", help="run deterministic evidence operations")
    engine_commands = engine.add_subparsers(dest="engine_command", required=True)
    analyze = engine_commands.add_parser("analyze", help="analyze structured observations")
    analyze.add_argument("input", help="UTF-8 structured JSON input")
    analyze.add_argument("--output", required=True, help="artifact output directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    if args.command == "engine" and args.engine_command == "analyze":
        try:
            summary = EvidenceEngineService().analyze_file(args.input, args.output)
        except EngineInputError as exc:
            print(
                json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2
        print(
            json.dumps(
                {"status": "succeeded", **summary.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
