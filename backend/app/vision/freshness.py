"""Read-only sensor and vision staleness evaluation."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.sensors.projection import get_latest_sensor_states
from app.vision.projection import get_latest_vision_state
from app.vision.schemas import FreshnessItem, PerceptionFreshnessResponse


def get_perception_freshness(db: Session) -> PerceptionFreshnessResponse:
    """Evaluate source timestamps without changing stored events or projections."""

    settings = get_settings()
    now = datetime.now(timezone.utc)
    thresholds = {
        "MQ2": settings.sensor_mq2_stale_after_seconds,
        "DHT22": settings.sensor_dht22_stale_after_seconds,
    }
    sensor_states = {
        state.sensor_type: state for state in get_latest_sensor_states(db)
    }
    sensor_items = {
        sensor_type: _freshness_item(
            source_type=sensor_type,
            source_id=state.node_id,
            timestamp=state.timestamp,
            threshold_seconds=thresholds.get(sensor_type),
            now=now,
        )
        for sensor_type, state in sensor_states.items()
    }

    vision = get_latest_vision_state(db)
    detection = _freshness_item(
        source_type="vision_detection",
        source_id=vision.detection.frame.frame_id if vision.detection else None,
        timestamp=vision.detection.frame.timestamp if vision.detection else None,
        threshold_seconds=settings.vision_stale_after_seconds,
        now=now,
    )
    road_items = [
        _freshness_item(
            source_type="vision_road_evidence",
            source_id=road.road_roi_name,
            timestamp=road.frame.timestamp,
            threshold_seconds=settings.vision_stale_after_seconds,
            now=now,
        )
        for road in vision.road_evidence
    ]
    return PerceptionFreshnessResponse(
        mq2=sensor_items["MQ2"],
        dht22=sensor_items["DHT22"],
        button=sensor_items["BUTTON"],
        ir_a=sensor_items["IR_A"],
        ir_b=sensor_items["IR_B"],
        detection=detection,
        road_evidence=road_items,
    )


def _freshness_item(
    *,
    source_type: str,
    source_id: str | None,
    timestamp: datetime | None,
    threshold_seconds: float | None,
    now: datetime,
) -> FreshnessItem:
    if timestamp is None:
        return FreshnessItem(
            source_type=source_type,
            source_id=source_id,
            available=False,
            stale=None,
            age_seconds=None,
            timestamp=None,
        )
    timestamp_utc = _as_utc(timestamp)
    age_seconds = max(0.0, (now - timestamp_utc).total_seconds())
    return FreshnessItem(
        source_type=source_type,
        source_id=source_id,
        available=True,
        stale=(age_seconds > threshold_seconds if threshold_seconds is not None else None),
        age_seconds=age_seconds,
        timestamp=timestamp_utc,
    )


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
