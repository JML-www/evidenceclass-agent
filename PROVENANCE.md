# Provenance and migration ledger

This repository is a clean-room successor to the project-local
`lingmou-classroom-evidence-v3` baseline. The legacy directory is not copied into this
repository. Only behavior that is covered by characterization tests is eligible for migration.

## Frozen baseline

Recorded on 2026-08-06 (Asia/Shanghai):

| Item | Recorded value |
|---|---|
| Python | `3.14.5` |
| Test command | `python -m unittest discover -s tests -v` |
| Result | `Ran 14 tests in 0.032s`; `OK` |
| `build_evidence_pack.py` SHA-256 | `93239F7336782204FA977FA9D108E2E0C55453192CB30D1FAE5FDD50CD7FD7C7` |
| `tests/test_pipeline.py` SHA-256 | `7FE1D26DBA2C0868BF3229E999D9DE513DBD9CD7103C8EF9E09BD79AC514B220` |

The baseline was run with `PYTHONDONTWRITEBYTECODE=1`; its tests write report artifacts only
to operating-system temporary directories. No source or fixture in the legacy directory was
edited during this audit.

## Asset decisions

| Asset | Legacy source | Rights status | Migration method | Public | Notes |
|---|---|---|---|---|---|
| Validation and metric behavior | `scripts/build_evidence_pack.py` | Project-authored; recheck before release | Characterize, then rewrite as pure functions | Yes | No original monolithic file is copied |
| Video planning behavior | `scripts/prepare_video.py` | Project-authored; recheck before release | Rewrite planning only; exclude encoding side effects for now | Yes | No media is included |
| Segment merge behavior | `scripts/merge_segment_results.py` | Project-authored; recheck before release | Characterize and modularize | Yes | Uses synthetic segments |
| Showcase window behavior | `scripts/prepare_showcase_clips.py` | Project-authored; recheck before release | Rewrite global-time window calculation only | Yes | No clips are included |
| Legacy test intent | `tests/test_pipeline.py` | Project-authored; recheck before release | Map all 14 rules to focused pytest tests | Yes | Mapping is in `docs/characterization-matrix.md` |
| Legacy Skill instructions | `SKILL.md` | Project-authored; recheck before release | Requirements reference only | Not now | Runtime will not depend on a Skill file |
| Dashboard template and Web implementation | `assets/dashboard-template/` and reference site | Rights not fully verified | Exclude; redesign later from written requirements | No | Do not inspect during Web implementation |
| Real classroom media, real filenames, login state, and screenshots | External/private sources | Restricted or unnecessary | Exclude | No | Must never enter Git history or releases |

When rights cannot be established, the default decision is exclusion. Synthetic fixtures in
`fixtures/structured/` were rewritten with generic course data and filenames; they contain no
names, student IDs, local paths, screenshots, or media bytes.

## Phase 2 clean-room result

As of 2026-08-07, the new repository implements the written validation, metric, evidence,
artifact-role, and CLI requirements as independently organized modules. The legacy monolithic
generator and its dashboard template were not copied. All migrated behavior remains attributable
to the characterization matrix, synthetic fixtures, contract tests, or explicit phase-2
requirements.

## Phase 3 clean-room result

As of 2026-08-09, the relational schema, lifecycle tables, idempotency algorithm, object-key
layout, retention flow, Compose topology, and acceptance tests were written from the tutorial's
phase-3 requirements and public library contracts. No database schema, cloud credentials, media,
container volume, or storage implementation was copied from the legacy project or reference site.
Only synthetic bytes and generated UUIDs enter the phase-3 test suite.

## Phase 4 clean-room result

As of 2026-08-10, model capability contracts, Fake fixtures, error taxonomy, retry and budget
policies, SDK isolation, raw-response references, and evaluation tooling were authored from the
tutorial requirements and public provider/library interfaces. The optional local Qwen checkpoint
is user-owned, remains outside this repository, and is never copied, hashed in full, or committed.
Ten evaluation images are generated from original geometric pixels
at runtime and contain no classroom media or personal information. Qwen3.5-0.8B is declared only
as a temporary functional substitute, not a final model or accuracy baseline.

## Phase 5 clean-room result

As of 2026-08-11, the safe probe policy, deterministic extraction timeline, VAD/chunk merge,
limited visual vocabulary, OCR threshold policy, segment manifest, and evaluation code were
written from the tutorial requirements and public FFmpeg/faster-whisper/RapidOCR interfaces.
No legacy media-processing implementation or private classroom byte was copied.

All committed phase-5 trial metadata is synthetic. The thirty visual diagrams are rendered at
runtime from the versioned truth manifest in `evals/media/`; generated PNG, video, WAV, model
cache, raw responses, and evaluation reports stay under ignored runtime/output directories. The
five-minute ASR fixture is synthesized locally with an installed operating-system voice; OCR
fixtures are original slide, board, and no-text drawings. These fixtures support reproducibility
and error analysis, not claims about real students, schools, or classroom-model accuracy.

## Phase 6 clean-room result

As of 2026-08-15, source governance, parser/chunker behavior, retrieval filters, prompt boundaries,
citation validation, and evaluation tooling were written from the tutorial requirements and
public pypdf, SQLAlchemy, PostgreSQL, and pgvector interfaces. No private teaching material,
external article, hidden prompt, or reference-site content was copied into the knowledge base.

The two Markdown handbooks and 40 questions are original synthetic evaluation text. The generated
five-page PDF contains ten original security rules and is created only under ignored run or test
directories. Injection strings are adversarial test inputs, not executable scripts; the harness
does not visit their links. Perfect metrics on this small code-labelled synthetic set prove that
the retrieval and evaluation gates work, not that a learned embedding model will generalize to
real educational literature.
