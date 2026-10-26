"""Side-effect-free live AI shadow evaluation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ShadowObservation(BaseModel):
    mode: str = "LIVE_AI_SHADOW"
    status: str
    source_frame_id: str
    source_timestamp: datetime
    processed_at: datetime
    crop_geometry_version: str
    detections: list[dict[str, Any]] = Field(default_factory=list)
    road_observations: list[dict[str, Any]] = Field(default_factory=list)
    mapped_edge_ids: list[str] = Field(default_factory=list)
    incident_created: bool = False
    route_recalculated: bool = False
    mqtt_published: bool = False
    hardware_actuated: bool = False
    warnings: list[str] = Field(default_factory=list)


def evaluate_live_shadow(*, frame_id: str, timestamp: datetime, processed_at: datetime, crop_geometry_version: str, detections: list[dict[str, Any]], segmentations: list[dict[str, Any]]) -> ShadowObservation:
    """Summarize genuine inference without assigning physical roads or acting."""

    hazard = [item for item in detections if str(item.get("class_name", "")).upper() in {"FIRE", "SMOKE", "PERSON"}]
    roads = [item for item in segmentations if str(item.get("class_name", "")).upper() in {"ROAD_OBSTACLE", "POTHOLE"}]
    return ShadowObservation(
        status="OBSERVATIONS_PRESENT" if hazard or roads else "NO_RELEVANT_OBSERVATIONS",
        source_frame_id=frame_id,
        source_timestamp=timestamp,
        processed_at=processed_at,
        crop_geometry_version=crop_geometry_version,
        detections=hazard,
        road_observations=roads,
        mapped_edge_ids=[],
        warnings=["Observation only; production incident automation is disabled", "Physical road/ROI mapping is unverified; no PE edge is assigned"],
    )
