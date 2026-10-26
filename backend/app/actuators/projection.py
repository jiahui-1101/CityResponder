"""Read-only actuator status projections from immutable command events."""

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
RECENT_EVENT_LIMIT = 500
COMMAND_ADAPTER = TypeAdapter(ActuatorCommand)
ACK_ADAPTER = TypeAdapter(ActuatorAckMessage)


def get_actuator_status(db: Session) -> ActuatorStatusResponse:
    """Project publish, receipt, execution, timeout, and failure separately."""

    command_events = get_recent_events(
        db,
        event_type="actuator_command",
        limit=RECENT_COMMAND_LIMIT,
    )
    publish_events = get_recent_events(
        db,
        event_type="actuator_command_published",
        limit=RECENT_EVENT_LIMIT,
    )
    publish_failures = get_recent_events(
        db,
        event_type="actuator_command_publish_failed",
        limit=RECENT_EVENT_LIMIT,
    )
    uncertain_publishes = get_recent_events(
        db,
        event_type="actuator_command_publish_uncertain",
        limit=RECENT_EVENT_LIMIT,
    )
    ack_events = get_recent_events(
        db,
        event_type="actuator_ack",
        limit=RECENT_EVENT_LIMIT,
    )
    timeout_events = get_recent_events(
        db,
        event_type="actuator_ack_timeout",
        limit=RECENT_EVENT_LIMIT,
    )

    published_by_id = _latest_by_command(publish_events)
    failed_publish_by_id = _latest_by_command(publish_failures)
    uncertain_publish_by_id = _latest_by_command(uncertain_publishes)
    acks_by_id: dict[str, list] = {}
    for event in reversed(ack_events):
        acks_by_id.setdefault(event.entity_id, []).append(event)
    timeouts_by_id = _latest_by_command(timeout_events)

    commands: list[ActuatorCommandStatus] = []
    for event in command_events:
        try:
            command = COMMAND_ADAPTER.validate_python(event.payload)
        except ValidationError:
            continue

        command_id = command.command_id
        command_acks = acks_by_id.get(command_id, [])
        received_event = next(
            (item for item in command_acks if item.payload.get("ack_stage") == "received"),
            None,
        )
        terminal_ack = next(
            (
                item
                for item in reversed(command_acks)
                if item.payload.get("ack_stage") in {"execution_reported", "failed"}
            ),
            None,
        )
        timeout_event = timeouts_by_id.get(command_id)
        if command_id in failed_publish_by_id and command_id not in published_by_id:
            publish_status = "failed"
        elif command_id in uncertain_publish_by_id and command_id not in published_by_id:
            publish_status = "unknown"
        elif command_id in published_by_id:
            publish_status = "broker_confirmed"
        else:
            publish_status = "not_confirmed"

        if terminal_ack is not None:
            try:
                ack = ACK_ADAPTER.validate_python(terminal_ack.payload)
                ack_status = ack.status
            except ValidationError:
                ack_status = str(terminal_ack.payload.get("status", "INVALID"))
            ack_stage = str(terminal_ack.payload.get("ack_stage", "unknown"))
            command_state = "execution_reported" if ack_stage == "execution_reported" else "failed"
            ack_at = terminal_ack.created_at
            late_ack = bool(terminal_ack.payload.get("late"))
        elif timeout_event is not None:
            ack_status = None
            ack_stage = None
            decision = timeout_event.payload.get("retry_decision")
            command_state = "execution_unknown" if decision == "no_retry_execution_unknown" else "timed_out"
            ack_at = None
            late_ack = False
        elif command_id in uncertain_publish_by_id and command_id not in published_by_id:
            ack_status = None
            ack_stage = None
            command_state = "execution_unknown"
            ack_at = None
            late_ack = False
        elif received_event is not None:
            try:
                ack_status = ACK_ADAPTER.validate_python(received_event.payload).status
            except ValidationError:
                ack_status = "RECEIVED"
            ack_stage = "received"
            command_state = "received"
            ack_at = received_event.created_at
            late_ack = False
        else:
            ack_status = None
            ack_stage = None
            command_state = "waiting_for_ack" if publish_status == "broker_confirmed" else "waiting_for_publish"
            ack_at = None
            late_ack = False

        commands.append(
            ActuatorCommandStatus(
                command_id=command_id,
                node_id=command.node_id,
                command_type=command.command_type,
                payload=command.payload,
                sent_at=command.timestamp,
                publish_status=publish_status,
                ack_status=ack_status,
                ack_stage=ack_stage,
                command_state=command_state,
                received_at=received_event.created_at if received_event else None,
                ack_at=ack_at,
                late_ack=late_ack,
                physical_state_confirmed=False,
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


def _latest_by_command(events: list) -> dict[str, object]:
    """Return the newest immutable event for each command entity."""

    return {event.entity_id: event for event in events}
