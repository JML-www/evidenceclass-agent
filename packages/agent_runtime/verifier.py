"""Evidence-first publication checks for Agent-generated claims."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field


class AgentClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: str = "OBSERVATION"
    evidence_ids: list[str] = []
    citation_ids: list[str] = []
    numbers: list[float] = []
    scope: str = "segment"
    metric_key: str | None = None


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str
    code: str
    message: str


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    publishable: bool
    checked_claims: int
    issues: list[VerificationIssue] = []


class ClaimVerifier:
    _number = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")
    _causal = re.compile(r"\b(because|causes?|therefore|due to)\b|由于|因为|导致|因此|说明", re.I)
    _psychological = re.compile(
        r"\b(motivation|intent|attitude|engagement quality)\b|心理|动机|态度|认真程度", re.I
    )

    def verify(
        self,
        claims: Iterable[AgentClaim],
        *,
        workspace_id: str,
        job_id: str | None = None,
        evidence_ids: set[str] | frozenset[str] = frozenset(),
        citation_ids: set[str] | frozenset[str] = frozenset(),
        evidence_jobs: Mapping[str, str] | None = None,
        citation_workspaces: Mapping[str, str] | None = None,
        analysis_result: Mapping[str, object] | None = None,
        mode: str = "video",
        artifact_values: Mapping[str, object] | None = None,
    ) -> VerificationResult:
        claims = list(claims)
        issues: list[VerificationIssue] = []
        analysis_numbers = self._numbers(analysis_result or {})
        artifact_numbers = self._numbers(artifact_values or {})
        for claim in claims:
            for evidence_id in claim.evidence_ids:
                if evidence_id not in evidence_ids:
                    issues.append(
                        VerificationIssue(
                            claim_id=claim.claim_id,
                            code="UNKNOWN_EVIDENCE",
                            message=f"unknown evidence {evidence_id}",
                        )
                    )
                elif (
                    job_id is not None
                    and evidence_jobs is not None
                    and evidence_jobs.get(evidence_id) != job_id
                ):
                    issues.append(
                        VerificationIssue(
                            claim_id=claim.claim_id,
                            code="CROSS_JOB_EVIDENCE",
                            message=f"evidence {evidence_id} belongs to another job",
                        )
                    )
            for citation_id in claim.citation_ids:
                if citation_id not in citation_ids:
                    issues.append(
                        VerificationIssue(
                            claim_id=claim.claim_id,
                            code="UNKNOWN_CITATION",
                            message=f"unknown citation {citation_id}",
                        )
                    )
                elif (
                    citation_workspaces is not None
                    and citation_workspaces.get(citation_id) != workspace_id
                ):
                    issues.append(
                        VerificationIssue(
                            claim_id=claim.claim_id,
                            code="CROSS_WORKSPACE_CITATION",
                            message=f"citation {citation_id} belongs to another workspace",
                        )
                    )
            if (
                claim.kind in {"KNOWLEDGE", "OBSERVATION", "METRIC"}
                and not claim.evidence_ids
                and not claim.citation_ids
            ):
                issues.append(
                    VerificationIssue(
                        claim_id=claim.claim_id,
                        code="UNSUPPORTED_CLAIM",
                        message="claim has no evidence or citation",
                    )
                )
            if any(
                number not in analysis_numbers and number not in artifact_numbers
                for number in claim.numbers
            ):
                issues.append(
                    VerificationIssue(
                        claim_id=claim.claim_id,
                        code="NUMBER_NOT_IN_RESULT",
                        message="claim number is absent from AnalysisResult",
                    )
                )
            if mode == "image" and claim.scope == "lesson":
                issues.append(
                    VerificationIssue(
                        claim_id=claim.claim_id,
                        code="IMAGE_SCOPE_ESCALATION",
                        message="image evidence cannot support whole-lesson claims",
                    )
                )
            if self._causal.search(claim.text) and not claim.citation_ids:
                issues.append(
                    VerificationIssue(
                        claim_id=claim.claim_id,
                        code="UNSUPPORTED_CAUSALITY",
                        message="causal explanation lacks supporting citation",
                    )
                )
            if self._psychological.search(claim.text):
                issues.append(
                    VerificationIssue(
                        claim_id=claim.claim_id,
                        code="PSYCHOLOGICAL_INFERENCE",
                        message="observable behaviour cannot be upgraded to psychology",
                    )
                )
            if claim.metric_key is not None:
                metric_value = self._lookup(analysis_result or {}, claim.metric_key)
                if metric_value is None and 0.0 in claim.numbers:
                    issues.append(
                        VerificationIssue(
                            claim_id=claim.claim_id,
                            code="UNKNOWN_AS_ZERO",
                            message="unknown metric was rendered as zero",
                        )
                    )
                if metric_value is not None and artifact_values is not None:
                    artifact_metric_values = {
                        name: self._lookup(value, claim.metric_key)
                        for name, value in artifact_values.items()
                        if isinstance(value, Mapping)
                    }
                    if any(
                        value is not None and value != metric_value
                        for value in artifact_metric_values.values()
                    ):
                        issues.append(
                            VerificationIssue(
                                claim_id=claim.claim_id,
                                code="ARTIFACT_VALUE_MISMATCH",
                                message=(
                                    "report, JSON, CSV, or page value differs from AnalysisResult"
                                ),
                            )
                        )
        return VerificationResult(publishable=not issues, checked_claims=len(claims), issues=issues)

    @classmethod
    def _numbers(cls, value: object) -> set[float]:
        text = repr(value)
        numbers: set[float] = set()
        for raw in cls._number.findall(text):
            try:
                numbers.add(float(raw.rstrip("%")))
            except ValueError:
                continue
        return numbers

    @staticmethod
    def _lookup(value: Mapping[str, object], dotted_key: str) -> object | None:
        current: object = value
        for part in dotted_key.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return None
            current = current[part]
        return current
