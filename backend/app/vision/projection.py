"""Read-only latest vision projections from immutable event history."""

import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.events.repository import get_recent_events
from app.vision.schemas import (
    LatestVisionResponse,
    VisionDetectionMessage,
    VisionRoadMessage,
)


logger = logging.getLogger(__name__)
RECENT_VISION_EVENT_LIMIT = 100


def get_latest_vision_state(
    db: Session,
    *,
    event_limit: int = RECENT_VISION_EVENT_LIMIT,
) -> LatestVisionResponse:
    """Derive the newest detection and newest road result per ROI."""

    detection = _latest_detection(db, event_limit)
    road_evidence = _latest_road_evidence(db, event_limit)
    return LatestVisionResponse(
        available=detection is not None or bool(road_evidence),
        detection=detection,
        road_evidence=road_evidence,
    )


def _latest_detection(db: Session, event_limit: int) -> VisionDetectionMessage | None:
    for event in get_recent_events(
        db,
        event_type="vision_detection",
        limit=event_limit,
    ):
        try:
            return VisionDetectionMessage.model_validate(event.payload)
        except ValidationError:
            logger.warning("Skipping invalid stored vision detection event id=%s", event.id)
    return None


def _latest_road_evidence(db: Session, event_limit: int) -> list[VisionRoadMessage]:
    latest_by_roi: dict[str, VisionRoadMessage] = {}
    for event in get_recent_events(
        db,
        event_type="vision_road_evidence",
        limit=event_limit,
    ):
        try:
            road = VisionRoadMessage.model_validate(event.payload)
        except ValidationError:
            logger.warning("Skipping invalid stored vision road event id=%s", event.id)
            continue
        latest_by_roi.setdefault(road.road_roi_name, road)
    return [latest_by_roi[name] for name in sorted(latest_by_roi)]
