"""Vision-specific view of the centralized application settings."""

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings


@dataclass(frozen=True)
class VisionConfig:
    source: str
    camera_index: int
    frame_width: int
    frame_height: int
    detection_model: str
    segmentation_model: str
    building_roi_min_width_px: int
    building_roi_min_height_px: int
    min_road_width_px: int
    pixel_to_cm_scale: float | None
    detection_target_fps: float
    segmentation_target_fps: float
    building_roi_coordinates: str | None
    road_roi_coordinates: str | None
    hazard_roi_coordinates: str | None
    road_ir_mapping: str | None
    ir_conflict_occupancy_threshold: float | None
    ir_conflict_value_threshold: float | None
    detection_confidence_threshold: float | None
    segmentation_confidence_threshold: float | None


@lru_cache
def get_vision_config() -> VisionConfig:
    """Return cached vision settings without opening a camera or loading a model."""

    settings = get_settings()
    return VisionConfig(
        source=settings.vision_source,
        camera_index=settings.vision_camera_index,
        frame_width=settings.vision_frame_width,
        frame_height=settings.vision_frame_height,
        detection_model=settings.vision_detection_model,
        segmentation_model=settings.vision_segmentation_model,
        building_roi_min_width_px=settings.vision_building_roi_min_width_px,
        building_roi_min_height_px=settings.vision_building_roi_min_height_px,
        min_road_width_px=settings.vision_min_road_width_px,
        pixel_to_cm_scale=settings.vision_pixel_to_cm_scale,
        detection_target_fps=settings.vision_detection_target_fps,
        segmentation_target_fps=settings.vision_segmentation_target_fps,
        building_roi_coordinates=settings.vision_building_roi_coordinates,
        road_roi_coordinates=settings.vision_road_roi_coordinates,
        hazard_roi_coordinates=settings.vision_hazard_roi_coordinates,
        road_ir_mapping=settings.vision_road_ir_mapping,
        ir_conflict_occupancy_threshold=settings.vision_ir_conflict_occupancy_threshold,
        ir_conflict_value_threshold=settings.vision_ir_conflict_value_threshold,
        detection_confidence_threshold=settings.vision_detection_confidence_threshold,
        segmentation_confidence_threshold=settings.vision_segmentation_confidence_threshold,
    )
