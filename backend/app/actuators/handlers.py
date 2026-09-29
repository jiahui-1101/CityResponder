"""Raw actuator ACK ingestion into immutable events and live updates."""

import logging
from typing import Any

from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter

from app.core.database import SessionLocal
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread
from app.actuators.schemas import ActuatorAckMessage
from app.actuators.ack_waiter import notify_actuator_ack


logger = logging.getLogger(__name__)
ack_adapter = TypeAdapter(ActuatorAckMessage)


def handle_ack_message(topic: str, payload: Any) -> None:
    """Validate one raw MQTT ACK and persist it as an immutable event."""

    if not isinstance(payload, dict):
        logger.warning("Invalid actuator ACK on %s: JSON object required", topic)
        return

    try:
        ack = ack_adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning("Invalid actuator ACK on %s: %s", topic, exc.errors())
        return

    notify_actuator_ack(
        ack.command_id,
        ack.node_id,
        dict(payload),
        ack.timestamp,
    )

    db = SessionLocal()
    try:
        append_event(
            db,
            event_type="actuator_ack",
            entity_type="command",
            entity_id=ack.command_id,
            payload=payload,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to store actuator ACK from %s", topic)
        return
    finally:
        db.close()

    publish_live_update_from_thread(
        {
            "event_type": "actuator_ack",
            "topic": topic,
            "payload": payload,
        }
    )
