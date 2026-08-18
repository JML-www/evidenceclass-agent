# Phase-7 Agent Runtime Acceptance

## Scope

Phase 7 turns the earlier contracts, model gateway, media pipeline, and citable RAG into an
executable Agent Runtime. It does not include the asynchronous Worker, public HTTP API, SSE, or Web
product planned for phases 8 and 9.

The default acceptance is deterministic. LangGraph executes real conditional edges, but no paid or
local generative model is required. The Planner's structured output boundary is exercised with
validated fixtures so CI tests policy and orchestration rather than provider availability.

## Requirement Matrix

| Tutorial step | Implemented evidence | Acceptance evidence |
|---|---|---|
| 7.1 deterministic graph tests | Explicit image, video-with-audio, video-without-audio, invalid-asset, validation-repair, review, verification-revision, and publication routes | No-audio video never reaches `transcribe_audio`; image mode does not use video-only nodes |
| 7.2 Tool Registry | Versioned input/output Pydantic contracts, allow-list, workspace check, bounded retries, idempotency cache, and duplicate-registration rejection | Unknown tool, extra dangerous field, forbidden tool, and cross-workspace input are rejected |
| 7.3 constrained Planner | `AnalysisPlan` records goal, accepted steps, selected tools, deadline, policy notes, and prompt version | Image/audio/no-audio/transcript/rubric plans are bounded; identity and over-budget full-frame requests are rejected |
| 7.4 LangGraph | `StateGraph` nodes, `START`/`END`, conditional edges, thread ID, and `InMemorySaver`; graph version is written to state | Three distinct trajectories finish with the expected node sets |
| 7.5 checkpoint/recovery | In-memory test store plus transactional `SqlCheckpointStore`; state, plan, prompt version, hashes, and step status are persisted | Simulated death after `observe_media` resumes at validation and does not add another observation call |
| 7.6 human in the loop | `NEEDS_REVIEW`, immutable original observation, revised version, reviewer/time/note/revision fields, role check, and compare-and-set decision | Pending work cannot publish; unauthorized or duplicate decisions fail; approved review resumes |
| 7.7 Claim Verifier | Evidence/job, citation/workspace, numeric provenance, image scope, unknown-as-zero, artifact consistency, causal, and psychological checks | All 20 deliberately polluted drafts are blocked |
| 7.8 budgets/stops | Steps, model calls, tool retries, token input/output, cost, deadline, and repair-round limits | Persistent verifier failure stops after two revisions and enters review |

## Persistence

Migration `d70a6e2f31b4` adds:

- checkpoint state, accepted plan, and Planner prompt version to `agent_runs`;
- reviewer, decision time, note, revision, original payload, and revised payload to `review_items`.

Large media and model outputs remain object references in `AgentState`; checkpoint JSON contains
only the small typed state and IDs. SQLite upgrade/check/downgrade/upgrade proves migration
reversibility locally. The existing GitHub infrastructure job applies the same migration chain to
PostgreSQL.

## Reproducible Command

```powershell
.\scripts\accept-stage-7.ps1 -RunFull
```

Local result on 2026-08-18:

| Check | Result |
|---|---|
| Ruff | All checks passed |
| Phase-7 focused plus migration | 66 passed |
| Dependency consistency | No broken requirements found |
| Full regression | 180 passed, 4 skipped |
| Coverage | 85% combined statement/branch measure |
| Python compileall | Passed |
| Git diff whitespace check | Passed |

The four skips are explicit external-runtime gates:

1. optional local Qwen GPU runtime;
2. paid remote-model opt-in;
3. local PostgreSQL/Redis/MinIO services;
4. local PostgreSQL pgvector extension.

The first two are unchanged model-availability limits. The latter two run in the GitHub
infrastructure job with pinned services. A local pass does not pre-claim the next remote run; the
GitHub result remains the final PostgreSQL confirmation after push.

## Evidence Boundary

This phase proves orchestration, policy, persistence, recovery, and deterministic publication
checks. It does not prove classroom-model accuracy, real-LLM semantic verification quality, or a
production PostgreSQL LangGraph checkpointer under worker concurrency. Those claims require later
authorized model evaluation and the phase-8 Worker/API load path.
