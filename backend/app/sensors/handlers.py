"""Raw sensor ingestion from MQTT into immutable events and live updates."""

import logging
from typing import Any

from pydantic import ValidationError

from app.core.database import SessionLocal
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread
from app.sensors.schemas import sensor_message_adapter


logger = logging.getLogger(__name__)


def handle_sensor_message(topic: str, payload: Any) -> None:
    """Validate one raw MQTT sensor message and persist it as an event."""

    if not isinstance(payload, dict):
        logger.warning("Invalid sensor message on %s: JSON object required", topic)
        return

    try:
        sensor = sensor_message_adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning("Invalid sensor message on %s: %s", topic, exc.errors())
        return

    db = SessionLocal()
    try:
        event = append_event(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id=sensor.node_id,
            payload=payload,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to store sensor message from %s", topic)
        return
    finally:
        db.close()

    publish_live_update_from_thread(
        {
            "event_type": "sensor_reading",
            "event_id": event.id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": payload,
        }
    )
