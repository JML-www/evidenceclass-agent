"""I/O boundary for the deterministic Evidence Engine."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from .renderers import (
    render_actions_csv,
    render_evidence_csv,
    render_html,
    render_json,
    render_markdown,
)
from .result_builder import build_result

ARTIFACT_FILENAMES = (
    "dashboard.html",
    "classroom_analysis_report.md",
    "evidence_ledger.csv",
    "action_and_retest.csv",
    "analysis_data.json",
)


class EngineInputError(ValueError):
    """Raised when an input file cannot enter the deterministic engine."""


@dataclass(frozen=True)
class ArtifactSummary:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class EngineRunSummary:
    task_id: str
    analysis_mode: str
    elapsed_seconds: float
    artifacts: dict[str, ArtifactSummary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "analysis_mode": self.analysis_mode,
            "elapsed_seconds": self.elapsed_seconds,
            "artifacts": {name: asdict(item) for name, item in self.artifacts.items()},
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_all(result: dict[str, Any]) -> dict[str, str]:
    return {
        "dashboard.html": render_html(result),
        "classroom_analysis_report.md": render_markdown(result),
        "evidence_ledger.csv": render_evidence_csv(result),
        "action_and_retest.csv": render_actions_csv(result),
        "analysis_data.json": render_json(result),
    }


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.evidenceclass-tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class EvidenceEngineService:
    """Run validation, pure calculation, and presentation through one reusable service."""

    def analyze_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return build_result(payload)

    def analyze_file(self, input_path: str | Path, output_dir: str | Path) -> EngineRunSummary:
        started = perf_counter()
        source = Path(input_path)
        destination = Path(output_dir)
        try:
            raw = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise EngineInputError(f"cannot read input: {source}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EngineInputError(
                f"input is not valid JSON at line {exc.lineno}, column {exc.colno}"
            ) from exc
        if not isinstance(payload, dict):
            raise EngineInputError("input root must be a JSON object")

        try:
            result = self.analyze_payload(payload)
        except (TypeError, ValueError, KeyError) as exc:
            raise EngineInputError(str(exc)) from exc
        rendered = _render_all(result)
        if tuple(rendered) != ARTIFACT_FILENAMES:
            raise RuntimeError("renderer set does not match the five-artifact contract")

        try:
            destination.mkdir(parents=True, exist_ok=True)
            if not destination.is_dir():
                raise OSError("output path is not a directory")
            for filename, content in rendered.items():
                _atomic_write_text(destination / filename, content)
        except OSError as exc:
            raise EngineInputError(f"cannot write output directory: {destination}") from exc

        artifacts = {
            filename: ArtifactSummary(
                path=str((destination / filename).resolve()),
                sha256=_sha256(destination / filename),
                size_bytes=(destination / filename).stat().st_size,
            )
            for filename in ARTIFACT_FILENAMES
        }
        return EngineRunSummary(
            task_id=result["taskId"],
            analysis_mode=result["analysisMode"],
            elapsed_seconds=round(perf_counter() - started, 6),
            artifacts=artifacts,
        )
