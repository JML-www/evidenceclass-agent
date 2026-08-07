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
