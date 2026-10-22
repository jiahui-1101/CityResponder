"""Deterministic, policy-driven dispatch-matrix recommendations."""

from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.physical_actions.schemas import ActionCategory


class ActionRecommendation(BaseModel):
    """Generic recommendation data without physical command semantics."""

    action_category: ActionCategory | None = None
    action_type: str = Field(min_length=1)
    target: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class DispatchInput(BaseModel):
    """Auditable inputs available to a future dispatch matrix policy."""

    incident_decision_id: str
    incident_confirmed: bool | None
    final_severity: str | None
    severity_score: float | None = Field(default=None, ge=0.0, le=100.0)
    person_in_hazard: bool | None
    route_id: str | None = None
    route_version: int | None = Field(default=None, gt=0)
    selected_corridor: Literal["PRIMARY", "STANDBY"] | None = None
    route_status: str | None = None
    no_safe_route: bool | None = None
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class DispatchRecommendation(BaseModel):
    """Separate recommendation channels; no execution is implied."""

    recommendation_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    status: Literal["recommended", "not_evaluated", "unresolved"]
    dispatch_actions: list[ActionRecommendation] = Field(default_factory=list)
    traffic_actions: list[ActionRecommendation] = Field(default_factory=list)
    building_actions: list[ActionRecommendation] = Field(default_factory=list)
    policy_version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    generated_at: datetime


class DispatchMatrixPolicy(Protocol):
    """Explicit source-backed mapping from incident inputs to recommendations."""

    version: str

    def evaluate(self, dispatch_input: DispatchInput) -> DispatchRecommendation:
        """Return deterministic, non-executing recommendations."""


def build_dispatch_recommendation(
    dispatch_input: DispatchInput,
    policy: DispatchMatrixPolicy | None = None,
) -> DispatchRecommendation:
    """Build recommendations only when confirmed and policy-driven."""

    audit_references = [
        *dispatch_input.source_references,
        *dispatch_input.audit_references,
    ]
    if dispatch_input.incident_confirmed is not True:
        status: Literal["recommended", "not_evaluated", "unresolved"] = (
            "unresolved"
            if dispatch_input.incident_confirmed is None
            else "not_evaluated"
        )
        return DispatchRecommendation(
            status=status,
            reasons=["incident confirmation is not explicitly true"],
            warnings=["no actionable dispatch recommendation was generated"],
            audit_references=audit_references,
            generated_at=datetime.now(timezone.utc),
        )
    if policy is None:
        return DispatchRecommendation(
            status="not_evaluated",
            reasons=["dispatch matrix policy is not configured"],
            warnings=["dispatch, traffic, and building actions remain unresolved"],
            audit_references=audit_references,
            generated_at=datetime.now(timezone.utc),
        )

    try:
        recommendation = policy.evaluate(dispatch_input)
    except Exception as exc:
        return DispatchRecommendation(
            status="unresolved",
            reasons=[f"dispatch matrix policy failed: {exc}"],
            audit_references=audit_references,
            generated_at=datetime.now(timezone.utc),
        )
    if recommendation.status != "recommended":
        return recommendation.model_copy(
            update={
                "audit_references": audit_references + recommendation.audit_references,
            }
        )
    return recommendation.model_copy(
        update={
            "policy_version": getattr(policy, "version", None),
            "audit_references": audit_references + recommendation.audit_references,
        }
    )
