# Data card v1

The Stage 11 evaluation release (`stage-11-evaluation.v1`) is a reproducible, authorized,
synthetic fixture release. It contains 30 visual trials, four manually transcribed ASR trials,
six OCR trials, twelve structure records, 40 retrieval cases, and 50 Agent cases. It has no
private assets and does not claim real-model accuracy. Real VLM/ASR/OCR/LLM runs require explicit
provider authorization and are reported separately as skipped or failed when unavailable.

Known limitations: synthetic images/audio do not represent classroom diversity; four ASR samples
are a contract smoke test rather than a statistical accuracy claim; retrieval cases measure
deterministic ranking and citation boundaries, not internet coverage. The test split is fixed by
case id and must not be edited after a report is published.

