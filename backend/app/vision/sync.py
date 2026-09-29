"""Camera/IR timestamp synchronization and conflict evaluation."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.sensors.projection import get_latest_sensor_states
from app.vision.projection import get_latest_vision_state
from app.vision.schemas import RoadIRSyncEvidence


logger = logging.getLogger(__name__)
SYNC_TOLERANCE_MS = 750.0
SUPPORTED_IR_SENSORS = {"IR_A", "IR_B"}


def get_road_ir_sync(db: Session) -> list[RoadIRSyncEvidence]:
    """Compare latest road evidence with explicitly mapped IR readings."""

    settings = get_settings()
    mapping = _load_mapping(settings.vision_road_ir_mapping)
    sensor_states = {
        state.sensor_type: state
        for state in get_latest_sensor_states(db)
        if state.sensor_type in SUPPORTED_IR_SENSORS
    }
    vision = get_latest_vision_state(db)
    return [
        _evaluate_pair(
            road=road,
            ir_sensor=mapping.get(road.road_roi_name),
            ir_state=sensor_states.get(mapping.get(road.road_roi_name)),
            occupancy_threshold=settings.vision_ir_conflict_occupancy_threshold,
            ir_value_threshold=settings.vision_ir_conflict_value_threshold,
        )
        for road in vision.road_evidence
    ]


def _evaluate_pair(
    *,
    road: Any,
    ir_sensor: str | None,
    ir_state: Any,
    occupancy_threshold: float | None,
    ir_value_threshold: float | None,
) -> RoadIRSyncEvidence:
    vision_timestamp = _as_utc(road.frame.timestamp)
    if ir_sensor not in SUPPORTED_IR_SENSORS:
        return RoadIRSyncEvidence(
            road_roi_name=road.road_roi_name,
            vision_timestamp=vision_timestamp,
            ir_sensor=None,
            ir_timestamp=None,
            time_delta_ms=None,
            time_matched=None,
            conflict=None,
            conflict_reason="not_evaluated: road-to-IR mapping is not configured",
        )
    if ir_state is None or ir_state.timestamp is None:
        return RoadIRSyncEvidence(
            road_roi_name=road.road_roi_name,
            vision_timestamp=vision_timestamp,
            ir_sensor=ir_sensor,
            ir_timestamp=None,
            time_delta_ms=None,
            time_matched=None,
            conflict=None,
            conflict_reason="not_evaluated: no IR reading is available",
        )

    ir_timestamp = _as_utc(ir_state.timestamp)
    time_delta_ms = abs((vision_timestamp - ir_timestamp).total_seconds() * 1000)
    time_matched = time_delta_ms <= SYNC_TOLERANCE_MS
    if not time_matched:
        return RoadIRSyncEvidence(
            road_roi_name=road.road_roi_name,
            vision_timestamp=vision_timestamp,
            ir_sensor=ir_sensor,
            ir_timestamp=ir_timestamp,
            time_delta_ms=time_delta_ms,
            time_matched=False,
            conflict=True,
            conflict_reason="time mismatch: source timestamps exceed 750 ms",
        )

    if occupancy_threshold is None or ir_value_threshold is None:
        return RoadIRSyncEvidence(
            road_roi_name=road.road_roi_name,
            vision_timestamp=vision_timestamp,
            ir_sensor=ir_sensor,
            ir_timestamp=ir_timestamp,
            time_delta_ms=time_delta_ms,
            time_matched=True,
            conflict=None,
            conflict_reason=(
                "not_evaluated: vision/IR disagreement thresholds are not configured"
            ),
        )

    ir_value = _numeric_value(ir_state.value)
    if ir_value is None:
        return RoadIRSyncEvidence(
            road_roi_name=road.road_roi_name,
            vision_timestamp=vision_timestamp,
            ir_sensor=ir_sensor,
            ir_timestamp=ir_timestamp,
            time_delta_ms=time_delta_ms,
            time_matched=True,
            conflict=None,
            conflict_reason="not_evaluated: IR value is not numeric",
        )
    vision_indicates_obstacle = road.occupancy_ratio >= occupancy_threshold
    ir_indicates_obstacle = ir_value >= ir_value_threshold
    conflict = vision_indicates_obstacle != ir_indicates_obstacle
    return RoadIRSyncEvidence(
        road_roi_name=road.road_roi_name,
        vision_timestamp=vision_timestamp,
        ir_sensor=ir_sensor,
        ir_timestamp=ir_timestamp,
        time_delta_ms=time_delta_ms,
        time_matched=True,
        conflict=conflict,
        conflict_reason=(
            "vision/IR evidence disagrees"
            if conflict
            else "vision/IR evidence agrees"
        ),
    )


def _load_mapping(raw_mapping: str | None) -> dict[str, str]:
    if raw_mapping is None or not raw_mapping.strip():
        return {}
    try:
        parsed = json.loads(raw_mapping)
        if not isinstance(parsed, dict):
            raise ValueError("mapping must be a JSON object")
        return {
            str(road): str(sensor)
            for road, sensor in parsed.items()
            if str(sensor) in SUPPORTED_IR_SENSORS
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Invalid VISION_ROAD_IR_MAPPING; sync will be not_evaluated")
        return {}


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
