"""Regression coverage for the live vision-to-incident bridge."""

from datetime import datetime, timedelta, timezone

from app.fusion.runtime import build_runtime_incident_decision
from app.sensors.schemas import LatestSensorState
from app.vision.schemas import (
    BoundingBox,
    CoordinateSystem,
    Detection,
    FrameMetadata,
    FrameSourceType,
    FreshnessItem,
    PerceptionFreshnessResponse,
    PerceptionSnapshot,
    ROI,
    VisionDetectionMessage,
)


def _fresh(source_type: str, timestamp: datetime) -> FreshnessItem:
    return FreshnessItem(
        source_type=source_type,
        source_id=source_type,
        available=True,
        stale=False,
        age_seconds=0.1,
        timestamp=timestamp,
    )


def _snapshot(timestamp: datetime, index: int) -> PerceptionSnapshot:
    detection = VisionDetectionMessage(
        frame=FrameMetadata(
            frame_id=f"frame-{index}",
            timestamp=timestamp,
            source=FrameSourceType.CAMERA,
            width=1080,
            height=840,
            coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
        ),
        building_roi=ROI(name="building_a", x=460, y=350, width=340, height=360),
        detections=[
            Detection(
                class_name="FIRE",
                confidence=0.85,
                bounding_box=BoundingBox(x1=500, y1=400, x2=560, y2=470),
            )
        ],
        person_in_hazard=False,
        processing_timestamp=timestamp,
    )
    freshness = PerceptionFreshnessResponse(
        mq2=_fresh("MQ2", timestamp),
        dht22=_fresh("DHT22", timestamp),
        button=_fresh("BUTTON", timestamp),
        ir_a=_fresh("IR_A", timestamp),
        ir_b=_fresh("IR_B", timestamp),
        detection=_fresh("camera", timestamp),
    )
    sensors = [
        LatestSensorState(sensor_type="MQ2", value=1800, available=True, timestamp=timestamp),
        LatestSensorState(sensor_type="DHT22", value=48, available=True, timestamp=timestamp),
        LatestSensorState(sensor_type="BUTTON", value=False, available=True, timestamp=timestamp),
        LatestSensorState(sensor_type="IR_A", value=True, available=True, timestamp=timestamp),
        LatestSensorState(sensor_type="IR_B", value=True, available=True, timestamp=timestamp),
    ]
    return PerceptionSnapshot(
        generated_at=timestamp,
        sensors=sensors,
        detection=detection,
        person_in_hazard=False,
        road_evidence=[],
        freshness=freshness,
        road_sync=[],
    )


def test_three_consecutive_fire_windows_create_incident_decision() -> None:
    start = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)

    decision = build_runtime_incident_decision(
        [_snapshot(start + timedelta(seconds=index), index) for index in range(3)]
    )

    assert decision is not None
    assert decision.incident_confirmed is True
    assert decision.decision_status == "confirmed"
    assert decision.final_severity is not None
