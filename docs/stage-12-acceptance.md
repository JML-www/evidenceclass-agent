# Stage 12 acceptance — observability, reliability and performance

This stage makes the evidence-first agent operable: every log line, metric and event is
correlatable, the system degrades predictably under injected faults and load, and the performance
baseline states exactly what was measured and what was not.

## Deliverables

- `packages/observability/correlation.py` — the seven unified correlation identifiers
  (`request_id`, `workspace_id`, `job_id`, `run_id`, `step_id`, `tool_call_id`, `model_call_id`)
  carried in a `contextvars` scope, serialized into `X-*-ID` HTTP/Celery headers.
- `apps/api/main.py` — the request middleware binds the scope, echoes `X-Request-ID`/`X-Trace-ID`,
  records HTTP counter/histogram metrics and emits `api.request.failed` for 4xx/5xx.
- `apps/worker/queue.py` + `apps/worker/celery_app.py` — the in-process queue re-binds the caller's
  scope inside the worker thread; the Celery tasks rebuild it from task headers.
- `packages/observability/logging.py` — JSON formatter, stable dotted event names, and mandatory
  redaction of secrets, prompts, transcripts, chain-of-thought, personal data and media paths.
- `packages/observability/metrics.py` — counters, gauges and histograms with a Prometheus text
  exposition served by `GET /metrics`.
- `packages/observability/timing.py` — the per-run stage timeline
  (`upload_ms`, `queue_wait_ms`, `probe_ms`, `frame_extract_ms`, `asr_ms`, `ocr_ms`, `vlm_ms`,
  `retrieval_ms`, `agent_overhead_ms`, `artifact_ms`, `end_to_end_ms`) plus a memory sampler.
- `packages/observability/reliability.py` — one stable verdict per infrastructure failure
  (`RETRY`, `BACKPRESSURE`, `DEGRADE`, `FAIL`, `NEEDS_REVIEW`).
- `packages/observability/faults.py` — the ten-scenario deterministic fault-injection harness.
- `apps/worker/admission.py` — per-workspace concurrency/queue caps, duration-weighted estimates,
  single-task time/memory caps, self-pruning in-flight window and GPU-OOM degradation.
- `apps/api/main.py` — `GET /api/v1/queue/status`; `POST /jobs/{id}/start|retry|rerun` admit before
  creating work and return HTTP 429 `QUEUE_BACKPRESSURE` when the ceiling is reached.
- `evals/run_stage12_faults.py`, `evals/run_stage12_load.py`, `evals/run_stage12_panel.py`,
  `evals/run_stage12_benchmark.py` and `scripts/accept-stage-12.ps1`.

## Run

```powershell
Set-Location -LiteralPath "E:\biomedicine\基于大语言模型的课堂学习行为检测赋能平台-王子豪\evidenceclass-agent"
.\scripts\accept-stage-12.ps1
```

The gate runs `ruff`, the full `tests/unit` + `tests/integration` suite, the ten fault injections,
the queue-protection load probe, the panel probe and the offline benchmark.

## Expected results (offline, deterministic)

| Check | Expected |
|---|---|
| Fault injections | 10/10 recovered, none missing, incident report written |
| Queue load probe | 24 concurrent starts → exactly `limit` admitted, the rest 429 `QUEUE_BACKPRESSURE`, `health/live` stays 200 |
| Panel probe | one job completes; `evidenceclass_stage_agent_overhead_milliseconds` and `..._end_to_end_milliseconds` present with non-zero medians |
| Benchmark | four scenarios × five repeats; model stages reported `null` |
| Log schema | `validate_record` returns no violations for real records |

## Honest boundaries

- Real VLM/ASR/OCR/LLM/retrieval latency, tokens and cost are **not** measured: no provider
  authorization is recorded, so those stages are reported as unknown. No accuracy or latency is
  claimed from a deterministic adapter.
- The benchmark inputs are synthetic structured observations, not real classroom recordings; the
  byte sizes are the serialized observation payloads, not media file sizes.
- The fault harness is deterministic and offline. Redis/PostgreSQL/FFmpeg outages are reproduced
  through the real code paths (resilience policy, checkpoint resume, resource cleanup, idempotency,
  worker finalisation) with injected errors rather than live infrastructure failures.
- Percentiles are computed over five repeats on a shared workstation and inherit interpreter and
  disk noise; they are a regression baseline, not a capacity planning guarantee.
