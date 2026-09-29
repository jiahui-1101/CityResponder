"""Read-only unified perception snapshot for downstream decision logic."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.sensors.projection import get_latest_sensor_states
from app.vision.freshness import get_perception_freshness
from app.vision.projection import get_latest_vision_state
from app.vision.schemas import PerceptionSnapshot
from app.vision.sync import get_road_ir_sync


def get_perception_snapshot(db: Session) -> PerceptionSnapshot:
    """Combine existing projections and evaluations without persisting a snapshot."""

    sensors = get_latest_sensor_states(db)
    vision = get_latest_vision_state(db)
    freshness = get_perception_freshness(db)
    road_sync = get_road_ir_sync(db)

    unavailable_inputs = [
        f"sensor:{sensor.sensor_type}"
        for sensor in sensors
        if not sensor.available
    ]
    if vision.detection is None:
        unavailable_inputs.append("vision_detection")
    if not vision.road_evidence:
        unavailable_inputs.append("vision_road_evidence")
    if vision.road_evidence and not road_sync:
        unavailable_inputs.append("road_sync")

    warnings = _freshness_warnings(freshness)
    warnings.extend(
        f"road:{sync.road_roi_name}: {sync.conflict_reason}"
        for sync in road_sync
        if sync.conflict is True
    )
    return PerceptionSnapshot(
        generated_at=datetime.now(timezone.utc),
        sensors=sensors,
        detection=vision.detection,
        person_in_hazard=(
            vision.detection.person_in_hazard if vision.detection is not None else None
        ),
        road_evidence=vision.road_evidence,
        freshness=freshness,
        road_sync=road_sync,
        warnings=warnings,
        unavailable_inputs=unavailable_inputs,
    )


def _freshness_warnings(freshness: object) -> list[str]:
    items = [
        freshness.mq2,
        freshness.dht22,
        freshness.button,
        freshness.ir_a,
        freshness.ir_b,
        freshness.detection,
        *freshness.road_evidence,
    ]
    return [
        f"{item.source_type} is stale"
        for item in items
        if item.stale is True
    ]
