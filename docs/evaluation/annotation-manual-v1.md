# Annotation manual v1

## Scope

Annotators record only what is directly observable in an authorized asset. The six visual labels
are exactly `raise_hand`, `standing`, `reading_or_writing_visible`, `group_discussion_visible`,
`teacher_at_podium`, and `teacher_patrolling_visible`.

`count=0` means the label was inspected and not observed. `count=null` means visibility is
insufficient. A null value is not a negative example and must not be converted to zero. Confidence
is descriptive only; it cannot turn a sampled frame into a duration estimate.

Each annotation includes an asset/frame identifier, timestamp, camera/region, evidence note,
annotator id, and this manual version. Annotators must not infer identity, emotion, ability,
motivation, diagnosis, discipline, speaker role, or whole-lesson quality.

## Disagreement and audit

Two annotators independently label a 30-unit overlap set. Record raw labels, adjudicated labels,
the disagreement reason, and the adjudicator/manual version. Report Cohen's kappa for categorical
labels and preserve missing/unknown reasons; do not silently discard disagreements.

