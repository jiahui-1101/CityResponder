"""Raw sensor ingestion from MQTT into immutable events and live updates."""

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.events.repository import append_event, get_recent_events
from app.fusion.runtime import automatic_incident_coordinator
from app.live.service import publish_live_update_from_thread
from app.sensors.registry import allowed_sensor_node_ids
from app.sensors.schemas import sensor_message_adapter


logger = logging.getLogger(__name__)
SENSOR_TOPIC_TYPES = {
    "mq2": "MQ2",
    "dht22": "DHT22",
    "button": "BUTTON",
    "ir_a": "IR_A",
    "ir_b": "IR_B",
}
MAX_SENSOR_FUTURE_SKEW_SECONDS = 5.0
RECENT_SENSOR_EVENTS_FOR_ORDERING = 512


def handle_sensor_message(topic: str, payload: Any) -> None:
    """Validate one raw MQTT sensor message and persist it as an event."""

    if not isinstance(payload, dict):
        logger.warning("Invalid sensor message on %s: JSON object required", topic)
        return

    topic_prefix = get_settings().sensor_mqtt_topic_prefix.strip("/")
    topic_path = (
        topic[len(topic_prefix) + 1 :]
        if topic.startswith(f"{topic_prefix}/")
        else ""
    )
    expected_sensor_type = SENSOR_TOPIC_TYPES.get(topic_path)
    if expected_sensor_type is None:
        logger.warning("Ignoring sensor message on unsupported topic %s", topic)
        return

    try:
        sensor = sensor_message_adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning("Invalid sensor message on %s: %s", topic, exc.errors())
        return

    if sensor.sensor_type != expected_sensor_type:
        logger.warning(
            "Ignoring sensor message on %s: topic expects %s, payload says %s",
            topic,
            expected_sensor_type,
            sensor.sensor_type,
        )
        return
    if sensor.node_id not in allowed_sensor_node_ids():
        logger.warning("Ignoring sensor message from unregistered node %s", sensor.node_id)
        return

    source_timestamp = sensor.timestamp.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if (source_timestamp - now).total_seconds() > MAX_SENSOR_FUTURE_SKEW_SECONDS:
        logger.warning("Ignoring future-dated sensor message from node %s", sensor.node_id)
        return

    db = SessionLocal()
    try:
        recent_events = get_recent_events(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id=sensor.node_id,
            limit=RECENT_SENSOR_EVENTS_FOR_ORDERING,
        )
        latest_source_timestamp = None
        for recent_event in recent_events:
            try:
                previous = sensor_message_adapter.validate_python(recent_event.payload)
            except ValidationError:
                continue
            if previous.sensor_type != sensor.sensor_type:
                continue
            previous_timestamp = previous.timestamp.astimezone(timezone.utc)
            if sensor.message_id is not None and previous.message_id == sensor.message_id:
                logger.info(
                    "Ignoring duplicate sensor message node=%s type=%s id=%s",
                    sensor.node_id,
                    sensor.sensor_type,
                    sensor.message_id,
                )
                return
            if (
                latest_source_timestamp is None
                or previous_timestamp > latest_source_timestamp
            ):
                latest_source_timestamp = previous_timestamp

        if (
            latest_source_timestamp is not None
            and source_timestamp <= latest_source_timestamp
        ):
            logger.info(
                "Ignoring duplicate or out-of-order sensor timestamp node=%s type=%s",
                sensor.node_id,
                sensor.sensor_type,
            )
            return

        event = append_event(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id=sensor.node_id,
            payload=payload,
        )
        try:
            automatic_incident_coordinator.observe(db)
        except Exception:
            logger.exception("Automatic incident fusion failed for %s", topic)
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
