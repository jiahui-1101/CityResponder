"""Risk-adjusted routing edge-cost calculation."""

from datetime import datetime, timezone
from math import isclose
from typing import Literal

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.factors import RoutingFactorEvaluation
from app.routing.safety import EdgeSafetyDecision
from app.routing.topology import RoutingEdge


ROUTING_WEIGHTS: dict[str, float] = {
    "O": 0.70,
    "L": 0.20,
    "routing_C": 0.10,
}


class EdgeCostResult(BaseModel):
    """Auditable cost result without graph mutation or route selection."""

    edge_id: str
    status: Literal["calculated", "excluded", "unresolved", "not_calculated"]
    distance_cm: float | None
    o: float | None
    l: float | None
    routing_c: float | None
    weights: dict[str, float]
    weighted_risk: float | None
    risk_multiplier: float | None
    edge_cost: float | None
    excluded_from_active_graph: bool | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    calculated_at: datetime


def calculate_edge_cost(
    routing_edge: RoutingEdge,
    factors: RoutingFactorEvaluation,
    safety: EdgeSafetyDecision,
) -> EdgeCostResult:
    """Calculate the proposal edge cost only for a definitively safe edge."""

    _validate_weights()
    reasons: list[str] = []
    o, l, routing_c = factors.o, factors.l, factors.routing_c
    weighted_risk: float | None = None
    risk_multiplier: float | None = None
    edge_cost: float | None = None

    if safety.edge_id is not None and safety.edge_id != routing_edge.edge_id:
        reasons.append("safety decision edge_id does not match routing edge")
    if safety.exclude_from_active_graph is True:
        status: Literal["calculated", "excluded", "unresolved", "not_calculated"] = "excluded"
        reasons.append("edge is excluded by hard-block or sensor conflict")
    elif safety.exclude_from_active_graph is None:
        status = "unresolved"
        reasons.append("edge safety exclusion state is unresolved")
    elif safety.edge_id is not None and safety.edge_id != routing_edge.edge_id:
        status = "unresolved"
    else:
        missing = []
        if routing_edge.distance_cm is None or routing_edge.distance_cm <= 0:
            missing.append("positive distance_cm")
        if factors.status != "available":
            reasons.append(f"routing factors are {factors.status}")
        for name, value in (("O", o), ("L", l), ("routing_c", routing_c)):
            if value is None:
                missing.append(name)
            elif not 0.0 <= value <= 1.0:
                reasons.append(f"{name} is outside [0,1]")
        if missing:
            reasons.extend(f"missing or invalid {item}" for item in missing)
        if reasons:
            status = "not_calculated"
        else:
            weighted_risk = (
                ROUTING_WEIGHTS["O"] * o
                + ROUTING_WEIGHTS["L"] * l
                + ROUTING_WEIGHTS["routing_C"] * routing_c
            )
            if not 0.0 <= weighted_risk <= 1.0:
                reasons.append("weighted risk is outside [0,1]")
                status = "not_calculated"
            else:
                risk_multiplier = 1.0 + 4.0 * weighted_risk
                if not 1.0 <= risk_multiplier <= 5.0:
                    reasons.append("risk multiplier is outside [1,5]")
                    status = "not_calculated"
                else:
                    edge_cost = routing_edge.distance_cm * risk_multiplier
                    if edge_cost <= 0.0:
                        reasons.append("calculated edge cost must be positive")
                        edge_cost = None
                        status = "not_calculated"
                    else:
                        status = "calculated"

    return EdgeCostResult(
        edge_id=routing_edge.edge_id,
        status=status,
        distance_cm=routing_edge.distance_cm,
        o=o,
        l=l,
        routing_c=routing_c,
        weights=dict(ROUTING_WEIGHTS),
        weighted_risk=weighted_risk,
        risk_multiplier=risk_multiplier,
        edge_cost=edge_cost,
        excluded_from_active_graph=safety.exclude_from_active_graph,
        reasons=reasons,
        audit_references=(
            list(factors.audit_references) + list(safety.audit_references)
        ),
        calculated_at=datetime.now(timezone.utc),
    )


def _validate_weights() -> None:
    if not isclose(sum(ROUTING_WEIGHTS.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("routing weights must sum to 1.0")
