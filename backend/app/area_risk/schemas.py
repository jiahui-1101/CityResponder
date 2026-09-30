"""Source-grounded Area Risk Index contracts."""

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

AREA_RISK_WEIGHTS = {"F": 0.30, "R": 0.25, "E": 0.20, "A": 0.15, "M": 0.10}
if sum(AREA_RISK_WEIGHTS.values()) != 1.0:
    raise RuntimeError("area risk weights must sum to exactly 1.0")


class AreaRiskComponents(BaseModel):
    """Symbolic components; their meanings remain policy/provider-defined."""

    f: float | None = Field(default=None, ge=0, le=1)
    r: float | None = Field(default=None, ge=0, le=1)
    e: float | None = Field(default=None, ge=0, le=1)
    a: float | None = Field(default=None, ge=0, le=1)
    m: float | None = Field(default=None, ge=0, le=1)


class VerifiedIncidentReference(BaseModel):
    incident_decision_id: str
    operator_action: str
    operator_id: int | None = None
    action_timestamp: datetime
    event_id: int
    area_id: str | None = None


class VerifiedHistoryWindow(BaseModel):
    evaluation_time: datetime
    window_start: datetime
    window_end: datetime
    eligible_incidents: list[VerifiedIncidentReference] = Field(default_factory=list)
    excluded_record_count: int = 0
    excluded_reasons: list[str] = Field(default_factory=list)
    audit_references: list[dict[str, Any]] = Field(default_factory=list)


class AreaRiskResult(BaseModel):
    area_id: str
    status: str
    score: float | None
    weights: dict[str, float] = Field(default_factory=lambda: dict(AREA_RISK_WEIGHTS))
    f: float | None = None
    r: float | None = None
    e: float | None = None
    a: float | None = None
    m: float | None = None
    window_start: datetime
    window_end: datetime
    verified_incident_count: int = 0
    provider_name: str | None = None
    provider_version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[dict[str, Any]] = Field(default_factory=list)
    calculated_at: datetime


class AreaRiskComponentProvider(Protocol):
    """Future explicit provider for normalized F/R/E/A/M components."""

    name: str
    version: str

    def provide(self, history: VerifiedHistoryWindow) -> AreaRiskComponents:
        ...


def calculate_area_risk(
    components: AreaRiskComponents,
    *,
    area_id: str,
    evaluation_time: datetime | None = None,
    verified_incident_count: int = 0,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    provider_name: str | None = None,
    provider_version: str | None = None,
    audit_references: list[dict[str, Any]] | None = None,
) -> AreaRiskResult:
    """Calculate only when an explicit provider has supplied all five values."""

    now = evaluation_time or datetime.now(timezone.utc)
    end = window_end or now
    start = window_start or (end - timedelta(days=180))
    values = {"F": components.f, "R": components.r, "E": components.e, "A": components.a, "M": components.m}
    missing = [name for name, value in values.items() if value is None]
    reasons = [] if not missing else [f"component {name} has no explicit provider value" for name in missing]
    score = None if missing else 100 * sum(AREA_RISK_WEIGHTS[name] * float(value) for name, value in values.items())
    if score is not None and not 0 <= score <= 100:
        raise ValueError("calculated area risk score must be within [0, 100]")
    return AreaRiskResult(
        area_id=area_id,
        status="calculated" if score is not None else "not_evaluated",
        score=score,
        f=components.f,
        r=components.r,
        e=components.e,
        a=components.a,
        m=components.m,
        window_start=start,
        window_end=end,
        verified_incident_count=verified_incident_count,
        provider_name=provider_name,
        provider_version=provider_version,
        reasons=reasons,
        warnings=["F/R/E/A/M meanings and normalization are provider-defined"] if score is None else [],
        audit_references=audit_references or [],
        calculated_at=now,
    )
