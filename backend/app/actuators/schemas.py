"""Validated schemas for actuator commands and acknowledgements."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActuatorCommand(BaseModel):
    """Generic command envelope sent to an actuator node."""

    model_config = ConfigDict(extra="allow")

    command_id: str
    node_id: str
    command_type: str
    payload: dict[str, Any]
    timestamp: datetime


class ActuatorAckMessage(BaseModel):
    """Minimum fields required for an actuator ACK."""

    model_config = ConfigDict(extra="allow")

    command_id: str
    node_id: str
    status: str
    timestamp: datetime


class ActuatorCommandStatus(BaseModel):
    """Read-only status projection for one recent actuator command."""

    command_id: str
    node_id: str
    command_type: str
    payload: dict[str, Any]
    sent_at: datetime
    ack_status: str | None = None
    ack_at: datetime | None = None


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
