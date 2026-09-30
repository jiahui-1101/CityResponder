"""MQTT ingestion handlers for structured vision evidence."""

import logging
from typing import Any

from pydantic import ValidationError

from app.core.database import SessionLocal
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread
from app.vision.schemas import VisionDetectionMessage, VisionRoadMessage


logger = logging.getLogger(__name__)


def handle_detection_message(topic: str, payload: Any) -> None:
    """Validate and append one Building A vision detection message."""

    message = _validate_payload(topic, payload, VisionDetectionMessage, "detection")
    if message is None:
        return
    payload_data = message.model_dump(mode="json")
    _store_and_publish(
        topic=topic,
        event_type="vision_detection",
        entity_type="vision_frame",
        entity_id=message.frame.frame_id,
        payload=payload_data,
    )


def handle_road_message(topic: str, payload: Any) -> None:
    """Validate and append one road vision evidence message."""

    message = _validate_payload(topic, payload, VisionRoadMessage, "road")
    if message is None:
        return
    payload_data = message.model_dump(mode="json")
    _store_and_publish(
        topic=topic,
        event_type="vision_road_evidence",
        entity_type="road_roi",
        entity_id=f"{message.frame.frame_id}:{message.road_roi_name}",
        payload=payload_data,
    )


def _validate_payload(
    topic: str,
    payload: Any,
    schema: type[VisionDetectionMessage] | type[VisionRoadMessage],
    label: str,
) -> VisionDetectionMessage | VisionRoadMessage | None:
    if not isinstance(payload, dict):
        logger.warning("Invalid vision %s message on %s: JSON object required", label, topic)
        return None
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Invalid vision %s message on %s: %s", label, topic, exc.errors())
        return None


def _store_and_publish(
    *,
    topic: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> None:
    db = SessionLocal()
    try:
        event = append_event(
            db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to store vision message from %s", topic)
        return
    finally:
        db.close()

    publish_live_update_from_thread(
        {
            "event_type": event_type,
            "event_id": event.id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": payload,
        }
    )
