"""Deterministic physical-command sequencing without execution."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.physical_actions.mapper import PhysicalActionPlan
from app.physical_actions.schemas import (
    ActionCategory,
    ActionType,
    PhysicalActionCommandSpec,
)


class SequencePhase(str, Enum):
    SAFETY_TRANSITION = "SAFETY_TRANSITION"
    TRAFFIC_CORRIDOR = "TRAFFIC_CORRIDOR"
    BUILDING_RESPONSE = "BUILDING_RESPONSE"


class PhysicalCommandPhase(BaseModel):
    """One ordered phase in a planned command sequence."""

    phase: SequencePhase
    command_specs: list[PhysicalActionCommandSpec] = Field(default_factory=list)
    delay_before_ms: int = Field(default=0, ge=0)
    delay_after_ms: int = Field(default=0, ge=0)


class PhysicalCommandSequence(BaseModel):
    """Auditable execution plan, not an execution result."""

    sequence_id: str
    status: str
    route_id: str | None = None
    route_version: int | None = Field(default=None, gt=0)
    phases: list[PhysicalCommandPhase] = Field(default_factory=list)
    ordered_command_specs: list[PhysicalActionCommandSpec] = Field(
        default_factory=list
    )
    source_plan_reference: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def sequence_physical_actions(plan: PhysicalActionPlan) -> PhysicalCommandSequence:
    """Plan safety, traffic, and building phases without real-time waiting."""

    base = dict(
        sequence_id=str(uuid4()),
        route_id=plan.route_id,
        route_version=plan.route_version,
        source_plan_reference=plan.source_recommendation_reference,
        generated_at=datetime.now(timezone.utc),
        audit_references=list(plan.audit_references),
    )
    if plan.status not in {"mapped", "partial"}:
        return PhysicalCommandSequence(
            status=plan.status,
            reasons=["physical action plan is not actionable"],
            warnings=list(plan.warnings),
            **base,
        )

    _validate_route_metadata(plan)
    traffic = [
        spec
        for spec in plan.command_specs
        if spec.action_category is ActionCategory.TRAFFIC
    ]
    building = [
        spec
        for spec in plan.command_specs
        if spec.action_category in {ActionCategory.GATE, ActionCategory.BUZZER}
    ]
    all_red = [
        spec for spec in traffic if spec.action_type is ActionType.ALL_RED
    ]
    green = [
        spec for spec in traffic if spec.action_type is ActionType.GREEN_CORRIDOR
    ]
    other_traffic = [
        spec
        for spec in traffic
        if spec.action_type not in {ActionType.ALL_RED, ActionType.GREEN_CORRIDOR}
    ]
    phases: list[PhysicalCommandPhase] = []
    warnings = list(plan.warnings)
    safety_commands = list(all_red)
    if green and not safety_commands:
        safety_commands.append(_required_all_red(green[0]))
        warnings.append("ALL_RED inserted as the required GREEN_CORRIDOR safety transition")
    if safety_commands:
        phases.append(
            PhysicalCommandPhase(
                phase=SequencePhase.SAFETY_TRANSITION,
                command_specs=safety_commands,
                delay_after_ms=1000 if green else 0,
            )
        )
    if green:
        phases.append(
            PhysicalCommandPhase(
                phase=SequencePhase.TRAFFIC_CORRIDOR,
                command_specs=green,
            )
        )
    if other_traffic:
        phases.append(
            PhysicalCommandPhase(
                phase=SequencePhase.TRAFFIC_CORRIDOR,
                command_specs=other_traffic,
            )
        )
    if building:
        phases.append(
            PhysicalCommandPhase(
                phase=SequencePhase.BUILDING_RESPONSE,
                command_specs=building,
            )
        )
    ordered = [spec for phase in phases for spec in phase.command_specs]
    return PhysicalCommandSequence(
        status="planned" if ordered else "not_evaluated",
        phases=phases,
        ordered_command_specs=ordered,
        reasons=list(plan.reasons),
        warnings=warnings,
        **base,
    )


def _required_all_red(green: PhysicalActionCommandSpec) -> PhysicalActionCommandSpec:
    return PhysicalActionCommandSpec(
        action_category=ActionCategory.TRAFFIC,
        action_type=ActionType.ALL_RED,
        target_node_id=green.target_node_id,
        route_id=green.route_id,
        route_version=green.route_version,
        source_recommendation_id=green.source_recommendation_id,
        reasons=["required before GREEN_CORRIDOR"],
        audit_references=list(green.audit_references),
    )


def _validate_route_metadata(plan: PhysicalActionPlan) -> None:
    for spec in plan.command_specs:
        if spec.route_id != plan.route_id or spec.route_version != plan.route_version:
            raise ValueError("inconsistent route metadata in physical action plan")
