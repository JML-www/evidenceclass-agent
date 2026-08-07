# EvidenceClass Agent

EvidenceClass Agent is an in-progress system for turning authorized, anonymized classroom
media into traceable observations, deterministic metrics, review tasks, and reports.

The repository currently contains the clean project skeleton, the migrated v3.1
characterization suite, strict Pydantic contracts v0.1, and a standalone deterministic
Evidence Engine. The engine validates structured observations, calculates descriptive metrics,
builds stable evidence and action records, and renders a hash-verified five-artifact package.
It does not yet contain model calls, an Agent runtime, an API, or a Web application.

## Current boundary

- Product layer: planned only; it will own upload, job progress, review, reporting, and Q&A.
- Agent layer: planned only; it will own planning, tool selection, branching, recovery, and
  human interruption.
- AI capability layer: planned only; it will contain replaceable ASR, OCR, VLM, LLM, embedding,
  and reranking adapters.
- Deterministic layer: phase 2 is implemented. Pure validation, metrics, sourced scoring,
  evidence IDs, result construction, presentation-only renderers, a reusable service, and the
  CLI own validation, metrics, evidence, hashes, and artifact consistency.

## Development setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Standalone engine CLI

The installed command calls `EvidenceEngineService`, the same in-process boundary that a future
Worker or Agent tool will use:

```powershell
evidenceclass engine analyze `
  ".\fixtures\structured\image-demo.json" `
  --output ".\runs\image-demo"
```

On success, the command prints the analysis mode, elapsed time, five artifact paths, byte sizes,
and SHA-256 hashes. Invalid input exits nonzero. The output writer replaces only the five managed
artifact names and preserves unrelated files in the destination directory.

See `docs/stage-2-acceptance.md` for the completed phase-2 acceptance matrix.

Only synthetic or explicitly authorized fixtures may enter this repository. See
`PROVENANCE.md` for the migration ledger and `SECURITY.md` for reporting instructions.
