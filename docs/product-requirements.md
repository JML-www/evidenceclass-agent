# Product requirements

This document is a clean-room requirements artifact. It records user goals, information,
states, and actions only. It deliberately excludes reference-site code, DOM structure, CSS
values, images, API fixtures, and wording.

## User stories

1. As a teacher, I can create an analysis job from authorized, anonymized media and see whether
   the upload is complete.
2. As a teacher, I can see queued, running, review-required, succeeded, failed, and cancelled
   jobs without confusing them with individual Agent or tool-call states.
3. As a reviewer, I can open an Agent run and see its plan, selected tools, retries, failures,
   and human-interruption points in chronological order.
4. As a reviewer, I can open a conclusion and jump to its Evidence ID, timestamp, source type,
   confidence, and limitations.
5. As a reviewer, I can filter observations that are missing evidence or require human review.
6. As a reviewer, I can approve, correct, or reject an observation without silently changing
   the original model output.
7. As a teacher, I can read a report whose numbers come from the deterministic result rather
   than being recomputed by an LLM.
8. As a teacher, I can ask a scoped question about a completed report and receive Evidence IDs
   or knowledge citations with the answer.
9. As a teacher, I am told explicitly when evidence is unavailable instead of receiving a
   guessed conclusion.
10. As an administrator, I can manage authorized rubric and knowledge sources with their
    version, citation, and activation state.
11. As an evaluator, I can run fixed datasets and inspect aggregate metrics, error slices, and
    the exact release configuration.
12. As an authorized user, I can compare aggregate results from two compatible runs without
    exposing or ranking individual students.

## Information architecture

| Page | User goal | Key information and states | Primary actions |
|---|---|---|---|
| Job center | Find and manage analyses | Job ID, mode, owner, created time, progress, job status, failure reason | Open, cancel, retry |
| New analysis | Submit authorized input | Input mode, files, observation goal, rubric, privacy acknowledgement | Validate, upload, submit |
| Agent run | Understand orchestration | Run state, nodes, decisions, tool calls, retries, checkpoints | Inspect step, resume after review |
| Evidence browser | Verify a claim | Evidence ID, source, global time, observation, limitations | Filter, jump to time, flag |
| Human review | Resolve uncertain output | Original observation, proposed correction, audit trail | Approve, edit, reject |
| Knowledge base | Manage cited guidance | Document, version, source, parsing/index state | Add, deactivate, rebuild |
| Evaluation center | Judge a release | Dataset, configuration, aggregate metrics, error slices | Run evaluation, compare releases |
| Settings | Configure capabilities | Adapter availability, retention, storage, access boundary | Test adapter, change policy |

## Non-goals for the current milestone

- Identifying, disciplining, ranking, or predicting the performance of individual students.
- Claiming diagnostic accuracy before an independently annotated evaluation exists.
- Inferring whole-lesson behavior from a single image or an unrepresentative clip.
- Importing the reference site's visual implementation or private data.
