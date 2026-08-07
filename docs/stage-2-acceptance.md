# Phase 2 acceptance record

This record maps tutorial steps 2.1 through 2.5 to executable repository evidence. It does not
claim that the Agent, model gateway, API, database, or Web product exists.

## Step 2.1: characterization baseline

- All 14 legacy rules map one-to-one to focused pytest tests in
  `docs/characterization-matrix.md`.
- Synthetic JSON fixtures contain no real names, local paths, screenshots, or media bytes.
- The formula mutation check is represented by focused lower-bound and aggregation tests.

## Step 2.2: contracts v0.1

- Nine public Pydantic contracts serialize `schema_version="contracts.v0.1"`.
- Unknown fields and five required illegal cross-field combinations fail validation.
- Failure tests assert the concrete Pydantic field location.

## Step 2.3: deterministic engine decomposition

| Responsibility | Module |
|---|---|
| Structured-input validation | `packages/evidence_engine/validation.py` |
| Pure ratios and aggregation | `packages/evidence_engine/metrics.py` |
| Weight normalization and sourced score | `packages/evidence_engine/scoring.py` |
| Stable Evidence IDs | `packages/evidence_engine/evidence.py` |
| Evidence-linked actions and retest | `packages/evidence_engine/actions.py` |
| Canonical semantic result | `packages/evidence_engine/result_builder.py` |
| JSON, CSV, Markdown, and offline HTML formatting | `packages/evidence_engine/renderers/` |
| File I/O and artifact hashes | `packages/evidence_engine/service.py` |

`metrics.py` has no file, network, database, random, or clock access. Renderers consume the
canonical result and do not import metric formulas. Repeating the same input produces identical
semantic results, Evidence IDs, and artifact bytes. Cross-artifact tests verify that metric values
and Evidence IDs come from `analysis_data.json` rather than being recalculated.

## Step 2.4: package and CLI

`pyproject.toml` installs the `evidenceclass` command. The supported invocation is:

```powershell
evidenceclass engine analyze `
  ".\fixtures\structured\image-demo.json" `
  --output ".\runs\image-demo"
```

Acceptance tests cover nonzero invalid-input exit status, preservation of unrelated output files,
the five output paths and SHA-256 hashes, and Windows paths containing Chinese characters and
spaces. `EvidenceEngineService` is the reusable in-process boundary; future Agent tools must not
shell out to the CLI.

## Step 2.5: property tests

The deterministic invariant property test uses Hypothesis with `max_examples=1000` and checks in
every generated example:

- percentages are `null` or within 0..100;
- a zero denominator yields `null`, never a fabricated zero;
- `not_visible` regions never enter comparisons;
- stable Evidence IDs do not repeat;
- nonzero rubric weights normalize to a sum of 1, while all-zero weights mean no score.

A fixed zero-denominator example is retained as a named regression test.

## Local acceptance commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests\unit\engine\test_properties.py --hypothesis-show-statistics -q
.\.venv\Scripts\python.exe -m pytest --cov=packages --cov-report=term-missing -q
git diff --check
```

Remote Windows Python 3.11 CI remains the final post-push confirmation.
