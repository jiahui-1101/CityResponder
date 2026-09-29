"""Unified, non-persistent incident decision assembly."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from app.fusion.schemas import (
    ConfirmationSequenceResult,
    ConfirmationWindowResult,
    FusionConfidenceResult,
    FusionSourceReference,
)
from app.severity.calculator import SeverityScoreResult
from app.severity.classification import SeverityClassificationResult


class IncidentDecision(BaseModel):
    """Auditable decision view assembled from existing evaluation results."""

    decision_id: str
    evaluated_at: datetime
    confirmation_status: str
    incident_confirmed: bool | None
    confirmation_windows: list[ConfirmationWindowResult] = Field(default_factory=list)
    fusion_confidence: FusionConfidenceResult
    severity_score: float | None
    base_severity: str | None
    final_severity: str | None
    critical_override_applied: bool
    decision_status: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def build_incident_decision(
    confirmation: ConfirmationSequenceResult,
    fusion_confidence: FusionConfidenceResult,
    severity_score: SeverityScoreResult,
    classification: SeverityClassificationResult,
) -> IncidentDecision:
    """Assemble a decision without recalculating or persisting any result."""

    confirmed = confirmation.incident_confirmed
    reasons = list(confirmation.reasons)
    reasons.extend(severity_score.reasons)
    reasons.extend(classification.reasons)
    warnings: list[str] = []

    if severity_score.incident_confirmed != confirmed:
        warnings.append(
            "severity score confirmation status differs from confirmation sequence"
        )
    if classification.critical_override_applied and confirmed is not True:
        warnings.append(
            "Critical classification exists while incident confirmation is not true"
        )
    if confirmed is True:
        decision_status = (
            "confirmed"
            if classification.final_severity is not None
            else "confirmed_severity_unresolved"
        )
    elif confirmed is False:
        decision_status = "not_confirmed"
        warnings.append("severity and actions are not actionable for an unconfirmed incident")
    else:
        decision_status = "unresolved"
        warnings.append("severity and actions are not actionable while confirmation is unresolved")

    audit_references = []
    audit_references.extend(confirmation.audit_references)
    audit_references.extend(fusion_confidence.audit_references)
    audit_references.extend(severity_score.audit_references)
    audit_references.extend(classification.audit_references)

    return IncidentDecision(
        decision_id=str(uuid4()),
        evaluated_at=datetime.now(timezone.utc),
        confirmation_status=confirmation.status,
        incident_confirmed=confirmed,
        confirmation_windows=list(confirmation.window_results),
        fusion_confidence=fusion_confidence,
        severity_score=severity_score.severity_score,
        base_severity=classification.base_severity,
        final_severity=classification.final_severity,
        critical_override_applied=classification.critical_override_applied,
        decision_status=decision_status,
        reasons=reasons,
        warnings=warnings,
        audit_references=audit_references,
    )
