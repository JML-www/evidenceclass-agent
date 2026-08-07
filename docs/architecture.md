# Architecture boundary

EvidenceClass Agent uses a modular monolith plus an asynchronous worker. The four logical
layers remain separate even while they live in one repository.

| Layer | Owns | Must not own |
|---|---|---|
| Product | Upload, jobs, progress, review, reports, and scoped Q&A | Metric calculation |
| Agent | Planning, tool selection, branches, recovery, and human interruption | Deterministic scoring formulas |
| AI capability | ASR, OCR, VLM, LLM, embedding, and reranking adapters | Business authorization |
| Deterministic | Schema, validation, metrics, evidence, hashes, and artifact consistency | Guesses about missing facts |

Planned request flow:

```text
Web -> API/control plane -> asynchronous worker -> Agent runtime
                                         |-> model gateway
                                         |-> retrieval
                                         `-> deterministic evidence engine
```

The current milestone completes tutorial phase 2. The deterministic engine is split into pure
validation, metrics, scoring, evidence, actions, and result-building modules. Presentation-only
renderers consume one canonical result, while `EvidenceEngineService` owns file I/O and the CLI
owns process exit behavior. A future Worker and Agent tool must call the service in-process rather
than launch the CLI as a subprocess. All Agent behavior remains future work; no Agent behavior is
claimed yet.
