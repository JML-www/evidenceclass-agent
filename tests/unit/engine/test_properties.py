import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from packages.evidence_engine.evidence import build_evidence
from packages.evidence_engine.metrics import (
    comparable_region_values,
    percentage_distribution,
    safe_percentage,
)
from packages.evidence_engine.scoring import normalize_weights


@settings(max_examples=1000, deadline=None, derandomize=True)
@given(
    denominator=st.integers(min_value=0, max_value=500),
    numerator=st.integers(min_value=0, max_value=1000),
    durations=st.dictionaries(
        keys=st.sampled_from(["teach", "discuss", "practice"]),
        values=st.integers(min_value=0, max_value=10_000),
        min_size=1,
        max_size=3,
    ),
    weights=st.dictionaries(
        keys=st.sampled_from(["focus", "participation", "interaction"]),
        values=st.floats(
            min_value=0,
            max_value=1000,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=3,
    ),
    facts=st.lists(
        st.sampled_from(["visible fact A", "visible fact B", "visible fact C"]),
        min_size=1,
        max_size=12,
    ),
)
def test_deterministic_engine_invariants_across_1000_generated_examples(
    denominator, numerator, durations, weights, facts
):
    percentage = safe_percentage(numerator, denominator)
    assert percentage is None or 0 <= percentage <= 100
    if denominator == 0:
        assert percentage is None

    distribution = percentage_distribution(durations)
    assert all(value is None or 0 <= value <= 100 for value in distribution.values())
    if sum(durations.values()) == 0:
        assert distribution and all(value is None for value in distribution.values())

    regions = [
        {"region_id": "hidden", "visibility": "not_visible", "metrics": {"focus": 100}},
        {"region_id": "visible", "visibility": "visible", "metrics": {"focus": percentage}},
    ]
    comparable = comparable_region_values(regions, "focus")
    assert all(region_id != "hidden" for region_id, _ in comparable)

    evidence_payload = {
        "analysisMode": "image",
        "frames": [
            {
                "frame_id": "same-source",
                "time": "current image",
                "evidence": facts,
                "confidence": 0.5,
            }
        ],
    }
    first_ids = [item.evidence_id for item in build_evidence(evidence_payload)]
    second_ids = [item.evidence_id for item in build_evidence(evidence_payload)]
    assert len(first_ids) == len(set(first_ids))
    assert first_ids == second_ids

    normalized = normalize_weights(weights)
    if sum(weights.values()) == 0:
        assert normalized == {}
    else:
        assert sum(normalized.values()) == pytest.approx(1.0)
        assert all(value >= 0 for value in normalized.values())


def test_zero_denominator_regression_is_unknown_not_zero():
    assert safe_percentage(0, 0) is None
    assert percentage_distribution({"teach": 0, "discuss": 0}) == {
        "teach": None,
        "discuss": None,
    }
