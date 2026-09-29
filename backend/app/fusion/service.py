"""Builder for the Part 3 incident-fusion input contract."""

from datetime import datetime

from app.sensors.schemas import LatestSensorState
from app.vision.schemas import PerceptionSnapshot

from app.fusion.schemas import (
    AuxiliaryFusionEvidence,
    FusionInput,
    FusionSourceReference,
    HistoricalBaselineChannel,
    SensorFusionChannel,
    TemporalFusionChannel,
    VisionFusionChannel,
)


SUPPORTED_SENSORS = ("MQ2", "DHT22", "BUTTON", "IR_A", "IR_B")


def build_fusion_input(perception_snapshot: PerceptionSnapshot) -> FusionInput:
    """Build explicit S/T/V/H boundaries without calculating any scores."""

    sensors = {
        sensor.sensor_type: sensor for sensor in perception_snapshot.sensors
    }
    for sensor_type in SUPPORTED_SENSORS:
        sensors.setdefault(sensor_type, LatestSensorState(sensor_type=sensor_type))

    sensor_references = [
        _sensor_reference(sensors[sensor_type])
        for sensor_type in ("MQ2", "DHT22")
        if sensors[sensor_type].available
    ]
    vision_references = _vision_references(perception_snapshot)
    temporal_references = _temporal_references(perception_snapshot)
    all_references = sensor_references + temporal_references + vision_references

    sensor_unavailable = [
        f"sensor:{sensor_type}"
        for sensor_type in ("MQ2", "DHT22")
        if not sensors[sensor_type].available
    ]
    vision_unavailable = (
        ["vision_detection"] if perception_snapshot.detection is None else []
    )
    historical = HistoricalBaselineChannel()
    unavailable_inputs = list(perception_snapshot.unavailable_inputs)
    unavailable_inputs.extend(sensor_unavailable)
    unavailable_inputs.extend(vision_unavailable)
    unavailable_inputs.append("historical_baseline")

    return FusionInput(
        generated_at=perception_snapshot.generated_at,
        s=SensorFusionChannel(
            mq2=sensors["MQ2"],
            dht22=sensors["DHT22"],
            source_references=sensor_references,
            unavailable_inputs=sensor_unavailable,
        ),
        t=TemporalFusionChannel(
            source_timestamps=_source_timestamps(perception_snapshot),
            freshness=perception_snapshot.freshness,
            source_references=temporal_references,
            unavailable_inputs=_temporal_unavailable(perception_snapshot),
        ),
        v=VisionFusionChannel(
            detection=perception_snapshot.detection,
            person_in_hazard=perception_snapshot.person_in_hazard,
            freshness=perception_snapshot.freshness.detection,
            source_references=vision_references,
            unavailable_inputs=vision_unavailable,
        ),
        h=historical,
        auxiliary=AuxiliaryFusionEvidence(
            button=sensors["BUTTON"],
            ir_a=sensors["IR_A"],
            ir_b=sensors["IR_B"],
            road_evidence=perception_snapshot.road_evidence,
        ),
        source_references=all_references,
        unavailable_inputs=unavailable_inputs,
    )


def _sensor_reference(sensor: LatestSensorState) -> FusionSourceReference:
    return FusionSourceReference(
        source_type=sensor.sensor_type,
        source_id=sensor.node_id or sensor.sensor_type,
        timestamp=sensor.timestamp,
    )


def _vision_references(
    perception_snapshot: PerceptionSnapshot,
) -> list[FusionSourceReference]:
    references: list[FusionSourceReference] = []
    if perception_snapshot.detection is not None:
        references.append(
            FusionSourceReference(
                source_type="vision_detection",
                source_id=perception_snapshot.detection.frame.frame_id,
                timestamp=perception_snapshot.detection.frame.timestamp,
            )
        )
    references.extend(
        FusionSourceReference(
            source_type="vision_road_evidence",
            source_id=road.road_roi_name,
            timestamp=road.frame.timestamp,
        )
        for road in perception_snapshot.road_evidence
    )
    return references


def _temporal_references(
    perception_snapshot: PerceptionSnapshot,
) -> list[FusionSourceReference]:
    return [
        FusionSourceReference(
            source_type=item.source_type,
            source_id=item.source_id or item.source_type,
            timestamp=item.timestamp,
        )
        for item in (
            perception_snapshot.freshness.mq2,
            perception_snapshot.freshness.dht22,
            perception_snapshot.freshness.detection,
            *perception_snapshot.freshness.road_evidence,
        )
        if item.available and item.timestamp is not None
    ]


def _source_timestamps(
    perception_snapshot: PerceptionSnapshot,
) -> dict[str, datetime | None]:
    freshness = perception_snapshot.freshness
    return {
        "MQ2": freshness.mq2.timestamp,
        "DHT22": freshness.dht22.timestamp,
        "vision_detection": freshness.detection.timestamp,
        **{
            f"vision_road:{item.source_id}": item.timestamp
            for item in freshness.road_evidence
        },
    }


def _temporal_unavailable(perception_snapshot: PerceptionSnapshot) -> list[str]:
    freshness = perception_snapshot.freshness
    return [
        item.source_type
        for item in (
            freshness.mq2,
            freshness.dht22,
            freshness.detection,
        )
        if not item.available
    ]
