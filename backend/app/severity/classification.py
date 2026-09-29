"""Severity classification and source-backed Critical override handling."""

from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.severity.calculator import SeverityScoreResult


class SeverityClassificationPolicy(Protocol):
    """Explicit source-backed policy for mapping R to a base severity."""

    version: str

    def classify(self, severity_score: float) -> str | None:
        """Return a deterministic base label for the supplied R score."""


class SeverityClassificationResult(BaseModel):
    """Auditable base classification and final override result."""

    status: str
    base_severity: str | None
    final_severity: str | None
    severity_score: float | None
    critical_override_applied: bool
    critical_override_signal: bool | None
    policy_version: str | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    classified_at: datetime


def classify_severity(
    score_result: SeverityScoreResult,
    policy: SeverityClassificationPolicy | None = None,
) -> SeverityClassificationResult:
    """Classify R only through an explicit policy, with a Critical override."""

    signal = score_result.critical_override_signal
    score = score_result.severity_score
    reasons: list[str] = []
    base_severity: str | None = None
    policy_version = getattr(policy, "version", None) if policy is not None else None

    if policy is None:
        reasons.append("severity classification policy is not configured")
    elif score is None:
        reasons.append("severity score is unavailable for base classification")
    else:
        base_severity = policy.classify(score)
        if base_severity is None:
            reasons.append("classification policy returned no base severity")

    if signal is True:
        return SeverityClassificationResult(
            status="overridden_critical",
            base_severity=base_severity,
            final_severity="CRITICAL",
            severity_score=score,
            critical_override_applied=True,
            critical_override_signal=True,
            policy_version=policy_version,
            reasons=reasons,
            audit_references=list(score_result.audit_references),
            classified_at=datetime.now(timezone.utc),
        )

    if signal is None:
        reasons.append("critical override signal is unresolved")
        return SeverityClassificationResult(
            status="unresolved",
            base_severity=base_severity,
            final_severity=None,
            severity_score=score,
            critical_override_applied=False,
            critical_override_signal=None,
            policy_version=policy_version,
            reasons=reasons,
            audit_references=list(score_result.audit_references),
            classified_at=datetime.now(timezone.utc),
        )

    if base_severity is None:
        reasons.append("base severity is unavailable without an explicit policy")
    return SeverityClassificationResult(
        status="classified" if base_severity is not None else "not_classified",
        base_severity=base_severity,
        final_severity=base_severity,
        severity_score=score,
        critical_override_applied=False,
        critical_override_signal=False,
        policy_version=policy_version,
        reasons=reasons,
        audit_references=list(score_result.audit_references),
        classified_at=datetime.now(timezone.utc),
    )
