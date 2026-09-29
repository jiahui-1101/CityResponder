"""Read-only actuator status projections from immutable events."""

from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter
from sqlalchemy.orm import Session

from app.actuators.schemas import (
    ActuatorAckMessage,
    ActuatorCommand,
    ActuatorCommandStatus,
    ActuatorNodeStatus,
    ActuatorStatusResponse,
)
from app.events.repository import get_recent_events


RECENT_COMMAND_LIMIT = 50
RECENT_ACK_LIMIT = 250
COMMAND_ADAPTER = TypeAdapter(ActuatorCommand)
ACK_ADAPTER = TypeAdapter(ActuatorAckMessage)


def get_actuator_status(db: Session) -> ActuatorStatusResponse:
    """Derive recent command/ACK state without mutating event history."""

    command_events = get_recent_events(
        db,
        event_type="actuator_command",
        limit=RECENT_COMMAND_LIMIT,
    )
    ack_events = get_recent_events(
        db,
        event_type="actuator_ack",
        limit=RECENT_ACK_LIMIT,
    )

    latest_acks: dict[str, ActuatorAckMessage] = {}
    for event in ack_events:
        try:
            ack = ACK_ADAPTER.validate_python(event.payload)
        except ValidationError:
            continue
        latest_acks.setdefault(ack.command_id, ack)

    commands: list[ActuatorCommandStatus] = []
    for event in command_events:
        try:
            command = COMMAND_ADAPTER.validate_python(event.payload)
        except ValidationError:
            continue

        ack = latest_acks.get(command.command_id)
        commands.append(
            ActuatorCommandStatus(
                command_id=command.command_id,
                node_id=command.node_id,
                command_type=command.command_type,
                payload=command.payload,
                sent_at=command.timestamp,
                ack_status=ack.status if ack else None,
                ack_at=ack.timestamp if ack else None,
            )
        )

    ac1_commands = [command for command in commands if command.node_id == "AC1"]
    ac1_acks = [command for command in ac1_commands if command.ack_at is not None]
    latest_ac1_ack = max(ac1_acks, key=lambda command: command.ack_at) if ac1_acks else None
    node_status = ActuatorNodeStatus(
        node_id="AC1",
        last_command_at=ac1_commands[0].sent_at if ac1_commands else None,
        last_ack_at=latest_ac1_ack.ack_at if latest_ac1_ack else None,
        last_ack_status=latest_ac1_ack.ack_status if latest_ac1_ack else None,
        available=bool(ac1_acks),
    )
    return ActuatorStatusResponse(commands=commands, node_status=node_status)
