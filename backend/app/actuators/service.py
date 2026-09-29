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

    append_event(
        db,
        event_type="actuator_command",
        entity_type="command",
        entity_id=command.command_id,
        payload=command_data,
    )
    mqtt_client.publish(topic, command_data, qos=1)
    publish_live_update_from_thread(
        {
            "event_type": "actuator_command",
            "topic": topic,
            "payload": command_data,
        }
    )
    return command_data
