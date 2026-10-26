"""Reusable backend service for publishing generic actuator commands."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.actuators.schemas import ActuatorCommand
from app.events.repository import append_event, get_events_for_entity
from app.live.service import publish_live_update_from_thread
from app.mqtt.client import mqtt_client


def publish_actuator_command(
    db: Session,
    *,
    node_id: str,
    command_type: str,
    payload: dict[str, Any],
    command_id: str | None = None,
) -> dict[str, Any]:
    """Persist and publish one generic actuator command at QoS 1."""

    command = ActuatorCommand(
        command_id=command_id or str(uuid4()),
        node_id=node_id,
        command_type=command_type,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
    )
    command_data = command.model_dump(mode="json")
    topic = f"city/commands/{command.node_id}"

    prior_events = get_events_for_entity(
        db,
        entity_type="command",
        entity_id=command.command_id,
    )
    original_event = next(
        (item for item in prior_events if item.event_type == "actuator_command"),
        None,
    )
    if original_event is None:
        command_event_type = "actuator_command"
    else:
        original = ActuatorCommand.model_validate(original_event.payload)
        prior_action = original.payload
        retry_action = command.payload
        same_action = all(
            prior_action.get(key) == retry_action.get(key)
            for key in ("action_category", "action_type", "parameters", "spec_id")
        )
        if (
            original.node_id != command.node_id
            or original.command_type != command.command_type
            or not same_action
            or retry_action.get("attempt_number") != 2
            or retry_action.get("retry_of_command_id") != command.command_id
        ):
            raise ValueError("command_id is already assigned to a different command")
        command_event_type = "actuator_command_retry"

    event = append_event(
        db,
        event_type=command_event_type,
        entity_type="command",
        entity_id=command.command_id,
        payload=command_data,
    )
    publish_error: Exception | None = None
    try:
        mqtt_client.publish_confirmed(topic, command_data, qos=1)
    except Exception as exc:
        publish_error = exc
        uncertain = isinstance(exc, TimeoutError)
        failure_event_type = (
            "actuator_command_publish_uncertain"
            if uncertain
            else "actuator_command_publish_failed"
        )
        failure_event = append_event(
            db,
            event_type=failure_event_type,
            entity_type="command",
            entity_id=command.command_id,
            reason_code=("MQTT_CONFIRMATION_TIMEOUT" if uncertain else "MQTT_PUBLISH_FAILED"),
            human_readable_reason=(
                "Broker confirmation timed out; AC1 may have received the command"
                if uncertain
                else "Actuator command could not be published to MQTT"
            ),
            payload={
                "command_id": command.command_id,
                "node_id": command.node_id,
                "topic": topic,
                "publish_status": "unknown" if uncertain else "failed",
                "broker_confirmed": False,
                "device_received": None if uncertain else False,
            },
        )
        publish_live_update_from_thread(
            {
                "event_type": failure_event.event_type,
                "entity_type": failure_event.entity_type,
                "entity_id": failure_event.entity_id,
                "event_id": failure_event.id,
                "backend_event_at": failure_event.created_at.isoformat(),
                "payload": failure_event.payload,
            }
        )
    else:
        published_event = append_event(
            db,
            event_type="actuator_command_published",
            entity_type="command",
            entity_id=command.command_id,
            payload={
                "command_id": command.command_id,
                "node_id": command.node_id,
                "topic": topic,
                "qos": 1,
                "retained": False,
                "broker_confirmed": True,
                "device_received": False,
                "attempt_number": command.payload.get("attempt_number", 1),
            },
        )
        publish_live_update_from_thread(
            {
                "event_type": published_event.event_type,
                "entity_type": published_event.entity_type,
                "entity_id": published_event.entity_id,
                "event_id": published_event.id,
                "backend_event_at": published_event.created_at.isoformat(),
                "payload": published_event.payload,
            }
        )
    publish_live_update_from_thread(
        {
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "event_id": event.id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": command_data,
        }
    )
    if publish_error is not None:
        raise publish_error
    return command_data
