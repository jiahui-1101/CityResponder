"""Reusable backend service for publishing generic actuator commands."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.actuators.schemas import ActuatorCommand
from app.events.repository import append_event
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

    event = append_event(
        db,
        event_type="actuator_command",
        entity_type="command",
        entity_id=command.command_id,
        payload=command_data,
    )
    publish_error: Exception | None = None
    try:
        mqtt_client.publish(topic, command_data, qos=1)
    except Exception as exc:
        publish_error = exc
        failure_event = append_event(
            db,
            event_type="actuator_command_publish_failed",
            entity_type="command",
            entity_id=command.command_id,
            reason_code="MQTT_PUBLISH_FAILED",
            human_readable_reason="Actuator command could not be published to MQTT",
            payload={
                "command_id": command.command_id,
                "node_id": command.node_id,
                "topic": topic,
                "publish_status": "failed",
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
    publish_live_update_from_thread(
        {
            "event_type": "actuator_command",
            "event_id": event.id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": command_data,
        }
    )
    if publish_error is not None:
        raise publish_error
    return command_data
