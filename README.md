# EvidenceClass Agent

EvidenceClass Agent is an in-progress system for turning authorized, anonymized classroom
media into traceable observations, deterministic metrics, review tasks, and reports.

The repository currently contains the clean project skeleton, the migrated v3.1
characterization suite, and strict Pydantic contracts v0.1 for requests, observations,
evidence, results, and artifact manifests. It does not yet contain a complete evidence engine,
model calls, an Agent runtime, an API, or a Web application.

## Current boundary

- Product layer: planned only; it will own upload, job progress, review, reporting, and Q&A.
- Agent layer: planned only; it will own planning, tool selection, branching, recovery, and
  human interruption.
- AI capability layer: planned only; it will contain replaceable ASR, OCR, VLM, LLM, embedding,
  and reranking adapters.
- Deterministic layer: characterization tests, contracts v0.1, and selected media/metric pure
  functions are implemented; this layer owns validation, metrics, evidence, hashes, and artifact
  consistency.

## Development setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Only synthetic or explicitly authorized fixtures may enter this repository. See
`PROVENANCE.md` for the migration ledger and `SECURITY.md` for reporting instructions.
