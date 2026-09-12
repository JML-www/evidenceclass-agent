from __future__ import annotations

from packages.observability.faults import (
    FAULT_IDS,
    SCENARIOS,
    FaultOutcome,
    render_markdown,
    run_all,
)


def test_scenario_registry_matches_the_required_fault_ids():
    assert tuple(fault_id for fault_id, _ in SCENARIOS) == FAULT_IDS
    assert len(FAULT_IDS) == 10


def test_every_injected_fault_is_handled_as_designed():
    outcomes = run_all()
    assert len(outcomes) == len(FAULT_IDS)
    unrecovered = [item.fault_id for item in outcomes if not item.recovered]
    assert unrecovered == []


def test_every_outcome_documents_expectation_remediation_and_risk():
    for outcome in run_all():
        assert isinstance(outcome, FaultOutcome)
        assert outcome.injected and outcome.expected and outcome.actual
        assert outcome.remediation and outcome.residual_risk
        assert outcome.observed_code


def test_report_renders_every_fault_with_its_evidence():
    outcomes = run_all()
    markdown = render_markdown(outcomes)
    assert markdown.startswith("# Fault injection report 001")
    for fault_id in FAULT_IDS:
        assert f"`{fault_id}`" in markdown
    assert "## Remediation and residual risk" in markdown
    assert "**Evidence:**" in markdown


def test_fault_scenarios_bind_a_correlation_scope_that_is_released():
    from packages.observability import current

    run_all()
    assert current() is None
