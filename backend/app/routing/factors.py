"""Explicit routing O/L/routing-C factor evaluation contracts."""

from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.evidence import RoadEdgeEvidence


class RoutingFactorValues(BaseModel):
    """Values explicitly produced by a future routing factor policy."""

    o: float | None = Field(default=None, ge=0.0, le=1.0)
    l: float | None = Field(default=None, ge=0.0, le=1.0)
    routing_c: float | None = Field(default=None, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class RoutingFactorPolicy(Protocol):
    """Explicit source-backed policy for deriving routing factors."""

    def evaluate(self, edge_evidence: RoadEdgeEvidence) -> RoutingFactorValues:
        """Return normalized O/L/routing-C values without applying decisions."""


class RoutingFactorEvaluation(BaseModel):
    """Auditable factor output distinct from raw road evidence and fire C."""

    status: Literal["available", "incomplete", "not_evaluated"]
    o: float | None = Field(default=None, ge=0.0, le=1.0)
    l: float | None = Field(default=None, ge=0.0, le=1.0)
    routing_c: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_evidence: RoadEdgeEvidence
    raw_occupancy_ratio: float
    raw_max_obstacle_extent_px: float
    raw_max_obstacle_extent_cm: float | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    evaluated_at: datetime


def evaluate_routing_factors(
    edge_evidence: RoadEdgeEvidence,
    policy: RoutingFactorPolicy | None = None,
) -> RoutingFactorEvaluation:
    """Evaluate routing factors only through an explicit policy."""

    base = dict(
        raw_evidence=edge_evidence,
        raw_occupancy_ratio=edge_evidence.occupancy_ratio,
        raw_max_obstacle_extent_px=edge_evidence.max_obstacle_extent_px,
        raw_max_obstacle_extent_cm=edge_evidence.max_obstacle_extent_cm,
        evaluated_at=datetime.now(timezone.utc),
    )
    if policy is None:
        return RoutingFactorEvaluation(
            status="not_evaluated",
            reasons=["routing factor policy is not configured"],
            audit_references=list(edge_evidence.source_references),
            **base,
        )

    try:
        values = policy.evaluate(edge_evidence)
        factors = {"O": values.o, "L": values.l, "routing_C": values.routing_c}
        invalid = [
            name
            for name, value in factors.items()
            if value is not None and not 0.0 <= value <= 1.0
        ]
        if invalid:
            raise ValueError(
                f"routing factor(s) outside [0,1]: {', '.join(invalid)}"
            )
        reasons = list(values.reasons)
        missing = [name for name, value in factors.items() if value is None]
        if missing:
            reasons.append(
                f"routing factor(s) are not evaluated: {', '.join(missing)}"
            )
        return RoutingFactorEvaluation(
            status="available" if not missing else "incomplete",
            o=values.o,
            l=values.l,
            routing_c=values.routing_c,
            reasons=reasons,
            audit_references=(
                list(edge_evidence.source_references) + list(values.audit_references)
            ),
            **base,
        )
    except Exception as exc:
        return RoutingFactorEvaluation(
            status="not_evaluated",
            reasons=[f"routing factor policy failed: {exc}"],
            audit_references=list(edge_evidence.source_references),
            **base,
        )
