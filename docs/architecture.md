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

The current milestone stops at tutorial step 2.2: it freezes deterministic behavior as
characterization tests and defines contracts v0.1 for cross-module data. The evidence engine
decomposition and all Agent behavior remain future work; no Agent behavior is claimed yet.
