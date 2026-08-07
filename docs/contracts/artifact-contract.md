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

The phase-2 engine implements the following output-role contract from one canonical semantic
result:

Required artifacts:

- `dashboard.html`
- `classroom_analysis_report.md`
- `evidence_ledger.csv`
- `action_and_retest.csv`
- `analysis_data.json`

The canonical JSON artifact emits `analysisMode` as `image` or `video`; typed Python contracts
use the `analysis_mode` field at module boundaries.

Renderers format deterministic results but do not import or call metric functions. The service
reports a SHA-256 hash and byte size for every artifact after writing. It overwrites only these
five managed names and never cleans unrelated output files.
