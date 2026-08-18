import pytest

from packages.agent_runtime import AgentClaim, ClaimVerifier

POLLUTED_DRAFTS = [
    (
        AgentClaim(claim_id="e1", text="unsupported", evidence_ids=["missing-1"]),
        {},
        "UNKNOWN_EVIDENCE",
    ),
    (
        AgentClaim(claim_id="e2", text="unsupported", evidence_ids=["missing-2"]),
        {},
        "UNKNOWN_EVIDENCE",
    ),
    (
        AgentClaim(claim_id="e3", text="cross job", evidence_ids=["e1"]),
        {"job_id": "job-a", "evidence_jobs": {"e1": "job-b"}},
        "CROSS_JOB_EVIDENCE",
    ),
    (
        AgentClaim(claim_id="e4", text="cross job again", evidence_ids=["e1"]),
        {"job_id": "job-a", "evidence_jobs": {"e1": "job-c"}},
        "CROSS_JOB_EVIDENCE",
    ),
    (
        AgentClaim(claim_id="c1", text="bad source", citation_ids=["missing-1"]),
        {},
        "UNKNOWN_CITATION",
    ),
    (
        AgentClaim(claim_id="c2", text="bad source", citation_ids=["missing-2"]),
        {},
        "UNKNOWN_CITATION",
    ),
    (
        AgentClaim(claim_id="c3", text="cross workspace", citation_ids=["c1"]),
        {"citation_workspaces": {"c1": "workspace-b"}},
        "CROSS_WORKSPACE_CITATION",
    ),
    (
        AgentClaim(claim_id="c4", text="cross workspace", citation_ids=["c1"]),
        {"citation_workspaces": {"c1": "workspace-c"}},
        "CROSS_WORKSPACE_CITATION",
    ),
    (
        AgentClaim(claim_id="n1", text="99 percent", evidence_ids=["e1"], numbers=[99]),
        {},
        "NUMBER_NOT_IN_RESULT",
    ),
    (
        AgentClaim(claim_id="n2", text="98 percent", evidence_ids=["e1"], numbers=[98]),
        {},
        "NUMBER_NOT_IN_RESULT",
    ),
    (
        AgentClaim(claim_id="n3", text="97 percent", evidence_ids=["e1"], numbers=[97]),
        {},
        "NUMBER_NOT_IN_RESULT",
    ),
    (
        AgentClaim(claim_id="n4", text="96 percent", evidence_ids=["e1"], numbers=[96]),
        {},
        "NUMBER_NOT_IN_RESULT",
    ),
    (
        AgentClaim(claim_id="s1", text="whole lesson", evidence_ids=["e1"], scope="lesson"),
        {"mode": "image"},
        "IMAGE_SCOPE_ESCALATION",
    ),
    (
        AgentClaim(
            claim_id="s2", text="all students all lesson", evidence_ids=["e1"], scope="lesson"
        ),
        {"mode": "image"},
        "IMAGE_SCOPE_ESCALATION",
    ),
    (
        AgentClaim(claim_id="l1", text="because the teacher caused it", evidence_ids=["e1"]),
        {},
        "UNSUPPORTED_CAUSALITY",
    ),
    (
        AgentClaim(claim_id="l2", text="therefore learning improved", evidence_ids=["e1"]),
        {},
        "UNSUPPORTED_CAUSALITY",
    ),
    (
        AgentClaim(claim_id="p1", text="student motivation is low", evidence_ids=["e1"]),
        {},
        "PSYCHOLOGICAL_INFERENCE",
    ),
    (
        AgentClaim(claim_id="p2", text="student attitude is poor", evidence_ids=["e1"]),
        {},
        "PSYCHOLOGICAL_INFERENCE",
    ),
    (
        AgentClaim(
            claim_id="u1",
            text="unknown is zero",
            evidence_ids=["e1"],
            numbers=[0],
            metric_key="unknown",
        ),
        {},
        "UNKNOWN_AS_ZERO",
    ),
    (
        AgentClaim(
            claim_id="a1",
            text="focus is 0.5",
            evidence_ids=["e1"],
            numbers=[0.5],
            metric_key="focus",
        ),
        {"analysis_result": {"focus": 0.5}, "artifact_values": {"json": {"focus": 0.7}}},
        "ARTIFACT_VALUE_MISMATCH",
    ),
]


@pytest.mark.parametrize(("claim", "overrides", "expected_code"), POLLUTED_DRAFTS)
def test_twenty_polluted_drafts_are_blocked(claim, overrides, expected_code):
    arguments = {
        "workspace_id": "workspace-a",
        "job_id": "job-a",
        "evidence_ids": {"e1"},
        "citation_ids": {"c1"},
        "analysis_result": {"focus": 0.5},
        "mode": "video",
    }
    arguments.update(overrides)
    result = ClaimVerifier().verify([claim], **arguments)
    assert result.publishable is False
    assert expected_code in {issue.code for issue in result.issues}
