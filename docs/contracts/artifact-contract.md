# Contracts v0.1

`packages/contracts` is the typed source of truth shared by future API, worker, model adapter,
evidence engine, and Agent runtime code. Every serialized model declares
`schema_version="contracts.v0.1"`, rejects unknown fields, and describes field units and
provenance in its generated JSON Schema.

The public contract surface contains:

- `AnalysisRequest`
- `FrameObservation`
- `TranscriptSegment`
- `OcrBlock`
- `RegionObservation`
- `EvaluationRubric`
- `EvidenceItem`
- `AnalysisResult`
- `ArtifactManifest`

Cross-field validation preserves the project boundaries: invisible regions cannot contain
numeric observations, image inputs cannot claim whole-lesson duration, behavior counts cannot
exceed visible students, teacher speaking ratio requires speaker diarization, and an unsourced
rubric cannot produce an overall score. Validation failures point to the offending field.

The following legacy output-role list remains a characterization source until renderers are
implemented in tutorial step 2.3:

Required artifacts:

- `dashboard.html`
- `classroom_analysis_report.md`
- `evidence_ledger.csv`
- `action_and_retest.csv`
- `analysis_data.json`

Legacy renderers must continue to emit `analysisMode` as `image` or `video`; new Python modules
use the typed `analysis_mode` field at contract boundaries.

Renderers may format deterministic results but must not recalculate metrics.
