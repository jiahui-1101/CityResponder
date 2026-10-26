"""Validated schemas for actuator commands and acknowledgements."""

from datetime import datetime, timezone
from typing import Literal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActuatorCommand(BaseModel):
    """Generic command envelope sent to an actuator node."""

    model_config = ConfigDict(extra="allow")

    command_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=32)
    command_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    timestamp: datetime


class ActuatorAckMessage(BaseModel):
    """Correlated AC1 receipt, execution report, or terminal failure."""

    model_config = ConfigDict(extra="allow")

    command_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=32)
    status: Literal["RECEIVED", "ACK", "EXECUTED", "FAILED", "REJECTED"]
    timestamp: datetime
    stage: Literal["received", "execution_reported", "failed"] | None = None
    result: str | None = None
    reason: str | None = None
    action_category: str | None = None
    action_type: str | None = None

    @model_validator(mode="after")
    def validate_stage(self) -> "ActuatorAckMessage":
        """Keep the device status and its meaning consistent."""

        expected = {
            "RECEIVED": "received",
            "ACK": "execution_reported",
            "EXECUTED": "execution_reported",
            "FAILED": "failed",
            "REJECTED": "failed",
        }[self.status]
        # Earlier AC1 firmware only sent status=ACK. Its ACK was emitted after
        # the output call, so that legacy form means execution was reported.
        if self.stage is not None and self.stage != expected:
            raise ValueError("ACK stage does not match status")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        return self


class ActuatorCommandStatus(BaseModel):
    """Read-only status projection for one recent actuator command."""

    command_id: str
    node_id: str
    command_type: str
    payload: dict[str, Any]
    sent_at: datetime
    publish_status: str = "not_confirmed"
    ack_status: str | None = None
    ack_stage: str | None = None
    command_state: str = "waiting_for_publish"
    received_at: datetime | None = None
    ack_at: datetime | None = None
    late_ack: bool = False
    physical_state_confirmed: bool = False


class ActuatorNodeStatus(BaseModel):
    """Read-only status projection for the AC1 node."""

    node_id: str
    last_command_at: datetime | None = None
    last_ack_at: datetime | None = None
    last_ack_status: str | None = None
    available: bool = False


class ActuatorStatusResponse(BaseModel):
    """Recent command projections plus AC1 status."""

    commands: list[ActuatorCommandStatus]
    node_status: ActuatorNodeStatus
