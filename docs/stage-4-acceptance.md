# Phase 4 acceptance record

This record separates the completed offline model-gateway boundary from real-model execution that
depends on an external endpoint or an optional multi-gigabyte local GPU runtime. It does not claim
that the phase-7 production Agent graph already exists.

## Step 4.1: unified capability interfaces

`packages/model_gateway/interfaces.py` defines runtime-checkable `ChatModel`, `VisionModel`,
`AsrModel`, `OcrModel`, `EmbeddingModel`, and `Reranker` Protocols. Their strict Pydantic requests
and results are provider-neutral. Every result envelope contains:

- provider, configured model, and returned model revision;
- prompt and config versions;
- latency, input/output tokens, characters, audio seconds, and cost or explicit unknown;
- a raw-response object reference rather than a body in logs;
- the parsed capability-specific structured result.

An architecture test scans all application and business packages and fails if they directly
import the OpenAI SDK. The SDK exists only inside the concrete compatible adapter.

## Step 4.2: complete Fake adapter and offline E2E

One versioned JSON fixture drives all six capabilities. Per-capability configuration supports:

- normal success;
- timeout;
- 429;
- 5xx;
- invalid JSON;
- Schema-shaped but semantically out-of-range output;
- one unavailable capability while other capabilities keep working.

`FakeStage4AcceptanceHarness` creates a durable Job and Agent Run, writes Step, Tool Call, and Model
Call traces, invokes Fake Vision, validates its structured result, calls the phase-2 deterministic
service, and publishes the exact five artifacts. The test replaces socket connection creation with
an exception, so passing proves this chain does not depend on network access, GPU, or model fees.
This harness is acceptance glue and is not mislabeled as the later production Agent graph.

## Step 4.3: one real path and current evidence

`OpenAICompatibleAdapter` implements real Chat and Vision calls with an explicit environment model,
server-side key, strict provider JSON Schema, local Pydantic semantic validation, zero SDK retries,
usage accounting, and raw-response storage by reference. No paid model is silently selected.

The opt-in evaluator generates exactly ten original PNG classroom diagrams in memory. It saves
Schema first-pass success rate, stable failure classes, latency, tokens, model revision, raw
references, and `accuracy_claimed=false`.

Current execution evidence is intentionally incomplete:

1. The available compatible endpoint allowed `/models` but rejected minimal Chat, Responses, and
   image generation requests with HTTP 403 `Your request was blocked`. The gateway now classifies
   this as non-retryable `MODEL_PERMISSION_DENIED`; repeating it cannot repair permissions.
2. The available local Qwen3.5-0.8B checkpoint is a genuine multimodal checkpoint with a vision
   encoder. It is suitable as a temporary functional substitute and is explicitly named
   `local-qwen-temporary` in metadata.
3. The pre-existing runtime used for other work has Torch 2.0.1 and Transformers 4.47.1, while
   this checkpoint needs Torch 2.4+ and a Transformers release containing `qwen3_5`. That
   environment was not modified.
4. A new isolated `.qwen-runtime` install was attempted. GPU PyTorch downloaded only about 69MB in
   ten minutes, so the process was stopped instead of waiting unboundedly. No ten-image local result
   is claimed yet.

Complete the optional local proof later with:

```powershell
$env:LOCAL_QWEN_MODEL_PATH = "C:\path\to\Qwen3.5-0.8B"
.\scripts\setup-local-qwen.ps1
.\scripts\accept-stage-4.ps1 -RunLocalQwen
```

This pending real-model evidence does not block later phases: every consumer depends on the six
Protocols, Fake remains the CI default, and either a corrected compatible endpoint or local Qwen
can be selected by configuration without changing business code.

## Step 4.4: bounded stability policies

The shared executor implements:

- bounded exponential backoff and injected random jitter for 429, selected 5xx, and timeouts;
- at most one constrained retry after JSON Schema parsing failure;
- no replay for authentication, permission, policy, or deterministic semantic errors;
- a sliding-window local rate limiter;
- a provider/model circuit breaker with cooldown;
- per-Job hard preflight ceilings for calls, token reservations, cost reservations, and wall time;
- rejection of unknown cost when a hard cost budget is required;
- sanitized SQL accounting for every success and failure attempt.

Tests prove the operation count and cost snapshot never exceed configured ceilings. A second
Alembic revision adds model revision, config version, characters, audio seconds, cost-known flag,
raw response reference, status, error code, and attempt number. Upgrade, downgrade, re-upgrade,
and metadata drift checks remain executable.

## Acceptance commands

Required offline gate:

```powershell
.\scripts\accept-stage-4.ps1
```

Optional remote compatible model, only with an explicitly authorized key and model:

```powershell
$env:RUN_REAL_MODEL_TESTS = "1"
$env:OPENAI_MODEL = "your-explicit-model"
.\.venv\Scripts\python.exe -m pytest tests\integration\test_real_model_smoke.py -q
```

Optional temporary local Qwen functional proof:

```powershell
$env:LOCAL_QWEN_MODEL_PATH = "C:\path\to\Qwen3.5-0.8B"
.\scripts\setup-local-qwen.ps1
.\scripts\accept-stage-4.ps1 -RunLocalQwen
```

Only successful structured-output counts may be called “success rate.” None of these smoke tests
measure classroom-model accuracy or justify a final provider decision.
