# Stage 11 acceptance — AI, RAG and Agent evaluation loop

This stage turns the existing evidence-first runtime into a reproducible evaluation loop. It is
deliberately fixture-first: fake adapters and deterministic baselines are valid for contract and
regression checks, while real provider calls are opt-in and cannot be reported as real accuracy
when credentials or authorization are absent.

## Deliverables

- `docs/evaluation/annotation-manual-v1.md` defines the six observable labels, null-versus-zero
  boundary, temporal/region rules, disagreement adjudication, and a 30-unit overlap audit.
- `docs/evaluation/data-card-v1.md` and `evals/datasets/manifest.v1.json` document authorized,
  synthetic fixtures, split policy, hashes/version fields, and known limitations.
- `evals/perception/evaluator.py` reports visual Precision/Recall/Macro-F1, count MAE and unknown
  rates; ASR CER by error category; OCR CER plus no-text false positives; and structure schema
  validity/missing/type/overclaim errors.
- `evals/retrieval/evaluator.py` reports Recall@5, MRR, nDCG@5, latency/cost fields when supplied,
  citation precision/recall, groundedness, refusal behaviour, and workspace leakage.
- `evals/agent/evaluator.py` validates 50 case records and reports route accuracy, tool selection,
  forbidden-tool rate, completion, human escalation, average steps, and evidence coverage.
- `evals/run_stage11_eval.py` writes JSON and Markdown reports under ignored `runs/stage-11/`.
- `scripts/accept-stage-11.ps1` is the repeatable local gate.

## Run

```powershell
Set-Location -LiteralPath "E:\biomedicine\基于大语言模型的课堂学习行为检测赋能平台-王子豪\evidenceclass-agent"
.\scripts\accept-stage-11.ps1
```

The offline report is expected to show 30 visual trials, 40 retrieval cases and 50 Agent cases,
zero workspace leakage, zero forbidden-tool selections, and all real-model tracks explicitly listed
as skipped unless a provider, model revision, authorization and credential scope are recorded.

## Version and failure policy

Every report records dataset version, evaluator version, code revision, prompt/policy version where
available, provider/model/revision, and skipped items. A changed label schema, prompt, citation
boundary or tool policy invalidates the relevant baseline and must fail the gate until a new version
is published. Failures include the case ids and evidence boundaries; no private prompts, secrets,
raw media paths, or model chain-of-thought are written to reports.

