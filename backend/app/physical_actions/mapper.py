"""Map explicit dispatch recommendations to physical command specifications."""

import json
from collections.abc import Mapping
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.dispatch.matrix import ActionRecommendation, DispatchRecommendation
from app.fusion.schemas import FusionSourceReference
from app.physical_actions.schemas import (
    DEFAULT_ACTUATOR_NODE_ID,
    ActionCategory,
    ActionType,
    PhysicalActionCommandSpec,
)


class SkippedAction(BaseModel):
    """An unsupported or invalid recommendation retained for auditability."""

    recommendation: ActionRecommendation
    reason: str


class PhysicalActionPlan(BaseModel):
    """Non-executing conversion of dispatch intent into command specs."""

    status: str
    command_specs: list[PhysicalActionCommandSpec] = Field(default_factory=list)
    skipped_actions: list[SkippedAction] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_recommendation_reference: str
    route_id: str | None = None
    route_version: int | None = None
    generated_at: datetime
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def map_dispatch_recommendation(
    recommendation: DispatchRecommendation,
    *,
    route_id: str | None = None,
    route_version: int | None = None,
    target_mapping: Mapping[str, str] | None = None,
) -> PhysicalActionPlan:
    """Convert only explicit supported actions; never execute them."""

    if route_version is not None and route_version <= 0:
        raise ValueError("route_version must be positive when supplied")

    base = dict(
        source_recommendation_reference=recommendation.recommendation_id,
        route_id=route_id,
        route_version=route_version,
        generated_at=datetime.now(timezone.utc),
        audit_references=list(recommendation.audit_references),
    )
    if recommendation.status != "recommended":
        return PhysicalActionPlan(
            status=recommendation.status,
            reasons=["dispatch recommendation is not actionable"],
            warnings=list(recommendation.warnings),
            **base,
        )

    specs: list[PhysicalActionCommandSpec] = []
    skipped: list[SkippedAction] = []
    warnings = list(recommendation.warnings)
    seen: set[tuple[str, str, str, str]] = set()
    actions = [
        *recommendation.dispatch_actions,
        *recommendation.traffic_actions,
        *recommendation.building_actions,
    ]
    for action in actions:
        try:
            category = action.action_category
            action_type = ActionType(action.action_type)
            if category is None:
                raise ValueError("action category is required")
            target = _target_for(category, action_type, target_mapping)
            _validate_json_parameters(action)
            spec = PhysicalActionCommandSpec(
                action_category=category,
                action_type=action_type,
                target_node_id=target,
                route_id=route_id,
                route_version=route_version,
                parameters=dict(action.parameters),
                source_recommendation_id=recommendation.recommendation_id,
                reasons=[action.reason] if action.reason else [],
                audit_references=list(recommendation.audit_references),
            )
        except (TypeError, ValueError) as exc:
            skipped.append(SkippedAction(recommendation=action, reason=str(exc)))
            continue
        identity = (
            spec.action_category.value,
            spec.action_type.value,
            spec.target_node_id,
            json.dumps(spec.parameters, sort_keys=True, allow_nan=False),
        )
        if identity in seen:
            warnings.append("exact duplicate physical action recommendation preserved")
        seen.add(identity)
        specs.append(spec)

    status = "mapped" if specs else "not_evaluated"
    if skipped and specs:
        status = "partial"
    reasons = list(recommendation.reasons)
    if not specs:
        reasons.append("no supported physical action specifications were produced")
    return PhysicalActionPlan(
        status=status,
        command_specs=specs,
        skipped_actions=skipped,
        reasons=reasons,
        warnings=warnings,
        **base,
    )


def _target_for(
    category: ActionCategory,
    action_type: ActionType,
    target_mapping: Mapping[str, str] | None,
) -> str:
    mapping = target_mapping or {}
    target = mapping.get(f"{category.value}:{action_type.value}")
    if target is None:
        target = mapping.get(category.value, DEFAULT_ACTUATOR_NODE_ID)
    if not target.strip():
        raise ValueError("configured actuator target must not be blank")
    return target


def _validate_json_parameters(action: ActionRecommendation) -> None:
    json.dumps(action.parameters, sort_keys=True, allow_nan=False)
