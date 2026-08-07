# Legacy characterization matrix

Baseline: `lingmou-classroom-evidence-v3/tests/test_pipeline.py`, SHA-256 recorded in
`PROVENANCE.md`. Each of its 14 tests maps to exactly one focused pytest test below.

| # | Legacy test | New test | File | Migration note |
|---:|---|---|---|---|
| 1 | `test_local_and_platform_contracts_match` | `test_artifact_contract_is_a_single_versioned_source` | `test_artifacts.py` | Rewritten to avoid two drifting contract documents |
| 2 | `test_image_mode_has_no_whole_lesson_inference` | `test_image_mode_disables_whole_lesson_metrics` | `test_validation.py` | Isolates the image capability boundary |
| 3 | `test_video_mode_has_timeline_and_behavior_share` | `test_video_mode_enables_timeline_and_duration_distributions` | `test_video_plan.py` | Isolates timeline and duration behavior from rendering |
| 4 | `test_image_mode_rejects_temporal_inputs` | `test_image_mode_rejects_temporal_observations` | `test_validation.py` | Preserves both ASR and teacher-event rejection |
| 5 | `test_invisible_region_cannot_have_numbers` | `test_not_visible_region_rejects_numeric_metrics` | `test_evidence.py` | Preserves missing-region semantics |
| 6 | `test_anonymize_removes_identifiers_and_local_paths` | `test_anonymization_removes_direct_identifiers_and_local_paths` | `test_artifacts.py` | Uses synthetic identifiers only |
| 7 | `test_large_video_plan_switches_to_ordered_parts` | `test_large_video_is_split_into_ordered_upload_parts` | `test_video_plan.py` | Preserves the bitrate and segment formula |
| 8 | `test_segment_merge_uses_global_time_and_weighted_ratio` | `test_segment_merge_converts_global_time_and_uses_duration_weights` | `test_segment_merge.py` | Preserves ordering, offset, sum, and weighted mean |
| 9 | `test_metric_values_are_bounded_or_unknown` | `test_frame_metrics_are_bounded_or_unknown` | `test_metrics.py` | Preserves `null` or 0..100 invariant |
| 10 | `test_overlapping_behavior_counts_use_a_lower_bound` | `test_overlapping_behaviors_use_visible_student_lower_bounds` | `test_metrics.py` | Locks the historical `max`, not `sum`, formula |
| 11 | `test_model_confidence_is_not_an_aggregation_weight` | `test_model_confidence_never_weights_metric_aggregation` | `test_metrics.py` | Duration is the only aggregation weight |
| 12 | `test_sourced_user_rubric_controls_weights_and_targets` | `test_sourced_rubric_controls_score_weights_and_alert_targets` | `test_metrics.py` | Isolates sourced scoring and target misses |
| 13 | `test_methodology_reference_documents_validation_boundary` | `test_methodology_states_validation_and_accuracy_boundaries` | `test_evidence.py` | Keeps citations and no-accuracy claim |
| 14 | `test_showcase_windows_preserve_global_context` | `test_showcase_windows_keep_global_timeline_offsets` | `test_artifacts.py` | Preserves global offsets without media |

The matrix intentionally does not copy the monolithic report builder or dashboard template.
Phase 2 later supplied new presentation-only renderers from the written artifact roles. Formula
tests remain active: changing the lower-bound calculation from `max` to `sum` makes the
corresponding targeted test fail.
