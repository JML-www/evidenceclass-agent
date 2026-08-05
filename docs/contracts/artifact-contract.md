# Artifact contract v0

This is the single characterization source for the five legacy output roles. It is not the
versioned Pydantic contract planned for tutorial step 2.2.

Required artifacts:

- `dashboard.html`
- `classroom_analysis_report.md`
- `evidence_ledger.csv`
- `action_and_retest.csv`
- `analysis_data.json`

Every future result must declare `analysisMode` as either `image` or `video`. Renderers may
format deterministic results but must not recalculate metrics.
