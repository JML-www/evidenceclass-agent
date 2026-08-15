# Evidence Policy

## E01 Authorization Gate

E01 authorization gate requires an explicit authorized status and a known license before a source version can be published.

## E02 Workspace Boundary

E02 workspace boundary applies tenant metadata before similarity scoring so another workspace can never enter the candidate set.

## E03 Stable Source Hash

E03 stable source hash compares the registered SHA-256 with the exact file bytes before document parsing begins.

## E04 Unknown Observation

E04 unknown observation keeps insufficient visual or audio evidence as unknown instead of inventing a classroom fact.

## E05 Sampled Occurrence

E05 sampled occurrence represents only a sampled timepoint and must not be converted into whole-lesson duration.

## E06 Speaker Role

E06 speaker role remains unknown when diarization is unavailable, which disables teacher-versus-student speech ratios.

## E07 OCR Raw Record

E07 OCR raw record remains stored even when confidence filtering removes every item from the presented text.

## E08 Evidence Provenance

E08 evidence provenance binds every observation to an asset, camera, global timestamp, policy version, and content hash.

## E09 Human Review

E09 human review is required for low-confidence or high-risk conclusions before a report becomes publishable.

## E10 Privacy Limit

E10 privacy limit prohibits face identity, student ranking, psychological diagnosis, and automatic disciplinary conclusions.
