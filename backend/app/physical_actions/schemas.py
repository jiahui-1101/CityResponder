"""Deterministic physical action vocabulary without execution behavior."""

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.fusion.schemas import FusionSourceReference


DEFAULT_ACTUATOR_NODE_ID = "AC1"


class ActionCategory(str, Enum):
    TRAFFIC = "TRAFFIC"
    GATE = "GATE"
    BUZZER = "BUZZER"


class ActionType(str, Enum):
    ALL_RED = "ALL_RED"
    GREEN_CORRIDOR = "GREEN_CORRIDOR"
    NORMAL_CYCLE = "NORMAL_CYCLE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    ON = "ON"
    OFF = "OFF"
    PULSE_500_MS = "PULSE_500_MS"


_CATEGORY_TYPES: dict[ActionCategory, set[ActionType]] = {
    ActionCategory.TRAFFIC: {
        ActionType.ALL_RED,
        ActionType.GREEN_CORRIDOR,
        ActionType.NORMAL_CYCLE,
        ActionType.OFF,
    },
    ActionCategory.GATE: {ActionType.OPEN, ActionType.CLOSE},
    ActionCategory.BUZZER: {
        ActionType.ON,
        ActionType.OFF,
        ActionType.PULSE_500_MS,
    },
}


class PhysicalActionCommandSpec(BaseModel):
    """Validated command specification compatible with generic AC1 commands."""

    spec_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    action_id: str | None = None
    safe_default: bool = False
    action_category: ActionCategory
    action_type: ActionType
    target_node_id: str = Field(default=DEFAULT_ACTUATOR_NODE_ID, min_length=1)
    route_id: str | None = None
    route_version: int | None = Field(default=None, gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_recommendation_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_compatibility(self) -> "PhysicalActionCommandSpec":
        allowed = _CATEGORY_TYPES[self.action_category]
        if self.action_type not in allowed:
            raise ValueError(
                f"action type {self.action_type.value} is not valid for "
                f"category {self.action_category.value}"
            )
        if not self.target_node_id.strip():
            raise ValueError("target_node_id is required")
        if self.action_type is ActionType.GREEN_CORRIDOR:
            corridor = self.parameters.get("corridor")
            if corridor not in {"PRIMARY", "STANDBY"}:
                raise ValueError(
                    "GREEN_CORRIDOR requires parameters.corridor "
                    "to be PRIMARY or STANDBY"
                )
        return self
