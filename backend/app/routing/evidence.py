"""Raw, auditable road-edge evidence for future routing decisions."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.sensors.schemas import LatestSensorState
from app.vision.schemas import (
    EvidenceDetectionReference,
    FreshnessItem,
    RoadIRSyncEvidence,
    VisionRoadMessage,
)


class RoadEdgeEvidence(BaseModel):
    """One logical road-edge evidence object without routing interpretation."""

    road_edge_id: str | None = None
    road_roi_name: str
    frame_id: str
    frame_timestamp: datetime
    frame_source: str
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    occupied_pixels: int = Field(ge=0)
    obstacle_count: int = Field(ge=0)
    max_obstacle_extent_px: float = Field(ge=0.0)
    max_obstacle_extent_cm: float | None = Field(default=None, ge=0.0)
    contributing_classes: list[str] = Field(default_factory=list)
    contributing_detections: list[EvidenceDetectionReference] = Field(
        default_factory=list
    )
    mapped_ir_sensor: str | None = None
    ir_timestamp: datetime | None = None
    ir_value: Any | None = None
    time_delta_ms: float | None = None
    time_matched: bool | None = None
    conflict: bool | None = None
    conflict_reason: str
    freshness: FreshnessItem | None = None
    available: bool
    stale: bool | None
    distance_cm: float | None = Field(default=None, ge=0.0)
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


def build_road_edge_evidence(
    road_evidence: VisionRoadMessage,
    *,
    sync: RoadIRSyncEvidence | None = None,
    ir_sensor_state: LatestSensorState | None = None,
    freshness: FreshnessItem | None = None,
    road_edge_id: str | None = None,
    source_references: list[FusionSourceReference] | None = None,
) -> RoadEdgeEvidence:
    """Build raw edge evidence without mapping or normalizing routing factors."""

    unavailable: list[str] = []
    mapped_ir_sensor = sync.ir_sensor if sync is not None else None
    if sync is None:
        unavailable.append("road_ir_sync")
    if mapped_ir_sensor is None:
        unavailable.append("road_to_ir_mapping")

    ir_timestamp = None
    ir_value = None
    if ir_sensor_state is not None:
        if mapped_ir_sensor is None or ir_sensor_state.sensor_type != mapped_ir_sensor:
            unavailable.append("mapped_ir_evidence")
        else:
            ir_timestamp = ir_sensor_state.timestamp
            ir_value = ir_sensor_state.value
            if not ir_sensor_state.available:
                unavailable.append("mapped_ir_evidence")
    elif mapped_ir_sensor is not None:
        unavailable.append("mapped_ir_evidence")

    if freshness is None:
        unavailable.append("road_freshness")
    elif not freshness.available:
        unavailable.append("road_freshness")

    return RoadEdgeEvidence(
        road_edge_id=road_edge_id,
        road_roi_name=road_evidence.road_roi_name,
        frame_id=road_evidence.frame.frame_id,
        frame_timestamp=road_evidence.frame.timestamp,
        frame_source=road_evidence.frame.source.value,
        occupancy_ratio=road_evidence.occupancy_ratio,
        occupied_pixels=road_evidence.occupied_pixels,
        obstacle_count=road_evidence.obstacle_count,
        max_obstacle_extent_px=road_evidence.max_obstacle_extent_px,
        max_obstacle_extent_cm=road_evidence.max_obstacle_extent_cm,
        contributing_classes=list(road_evidence.contributing_classes),
        contributing_detections=list(road_evidence.contributing_detections),
        mapped_ir_sensor=mapped_ir_sensor,
        ir_timestamp=ir_timestamp,
        ir_value=ir_value,
        time_delta_ms=sync.time_delta_ms if sync is not None else None,
        time_matched=sync.time_matched if sync is not None else None,
        conflict=sync.conflict if sync is not None else None,
        conflict_reason=(
            sync.conflict_reason
            if sync is not None
            else "road/IR synchronization is not evaluated"
        ),
        freshness=freshness,
        available=road_evidence.frame is not None
        and (freshness.available if freshness is not None else True),
        stale=freshness.stale if freshness is not None else None,
        distance_cm=None,
        source_references=list(source_references or []),
        unavailable_inputs=unavailable,
    )
