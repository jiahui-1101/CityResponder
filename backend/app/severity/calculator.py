"""Severity score calculation without severity classification."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.fusion.schemas import ConfirmationSequenceResult, FusionSourceReference
from app.severity.schemas import SeverityInput


SEVERITY_WEIGHTS: dict[str, float] = {
    "A": 0.30,
    "S": 0.20,
    "T": 0.20,
    "P": 0.20,
    "Z": 0.10,
}


class SeverityScoreResult(BaseModel):
    """Auditable result of applying the proposal severity formula."""

    status: Literal["calculated", "not_calculated"]
    severity_score: float | None
    a: float | None
    s: float | None
    t: float | None
    p: float | None
    z: float | None
    weights: dict[str, float]
    weighted_contributions: dict[str, float | None]
    incident_confirmed: bool | None
    confirmation_reference: ConfirmationSequenceResult | None
    critical_override_signal: bool | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    calculated_at: datetime


def calculate_severity_score(severity_input: SeverityInput) -> SeverityScoreResult:
    """Calculate R only for a confirmed incident with five valid components."""

    _validate_weights()
    values = {
        "A": severity_input.a,
        "S": severity_input.s,
        "T": severity_input.t,
        "P": severity_input.p,
        "Z": severity_input.z,
    }
    reasons: list[str] = []
    if severity_input.incident_confirmed is not True:
        reasons.append("incident confirmation is not explicitly true")
    for name, value in values.items():
        if value is None:
            reasons.append(f"severity component {name} is unavailable")
        elif not 0.0 <= value <= 1.0:
            reasons.append(f"severity component {name} is outside [0, 1]")

    contributions = {
        name: value * SEVERITY_WEIGHTS[name] if value is not None else None
        for name, value in values.items()
    }
    score = None
    status: Literal["calculated", "not_calculated"] = "not_calculated"
    if not reasons:
        score = 100.0 * sum(
            contributions[name] for name in SEVERITY_WEIGHTS
            if contributions[name] is not None
        )
        score = min(100.0, max(0.0, score))
        status = "calculated"
    return SeverityScoreResult(
        status=status,
        severity_score=score,
        a=severity_input.a,
        s=severity_input.s,
        t=severity_input.t,
        p=severity_input.p,
        z=severity_input.z,
        weights=dict(SEVERITY_WEIGHTS),
        weighted_contributions=contributions,
        incident_confirmed=severity_input.incident_confirmed,
        confirmation_reference=severity_input.confirmation_reference,
        critical_override_signal=severity_input.critical_override_signal,
        reasons=reasons,
        audit_references=list(severity_input.audit_references),
        calculated_at=datetime.now(timezone.utc),
    )


def _validate_weights() -> None:
    if not SEVERITY_WEIGHTS or abs(sum(SEVERITY_WEIGHTS.values()) - 1.0) > 1e-12:
        raise RuntimeError("severity weights must sum to 1.0")
