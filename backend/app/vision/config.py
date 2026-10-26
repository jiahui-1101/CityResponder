"""Vision-specific view of the centralized application settings."""

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings


@dataclass(frozen=True)
class VisionConfig:
    source: str
    camera_index: int | None
    capture_backend: str | None
    capture_fourcc: str | None
    frame_width: int
    frame_height: int
    detection_model: str
    segmentation_model: str
    inference_size: int
    inference_cpu_threads: int
    inference_device: str
    ai_display_target_fps: float
    require_exact_frame_size: bool
    display_crop_left: float
    display_crop_top: float
    display_crop_right: float
    display_crop_bottom: float
    polygon_roi_enabled: bool
    polygon_roi_config_path: str | None
    board_crop_coordinates: str | None
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
    publish_evidence: bool = False


@lru_cache
def get_vision_config() -> VisionConfig:
    """Return cached vision settings without opening a camera or loading a model."""

    settings = get_settings()
    return VisionConfig(
        source=settings.vision_source,
        camera_index=settings.vision_camera_index,
        capture_backend=settings.vision_capture_backend,
        capture_fourcc=settings.vision_capture_fourcc,
        frame_width=settings.vision_frame_width,
        frame_height=settings.vision_frame_height,
        detection_model=settings.detection_weights,
        segmentation_model=settings.segmentation_weights,
        inference_size=settings.vision_inference_size,
        inference_cpu_threads=settings.vision_inference_cpu_threads,
        inference_device=settings.vision_inference_device,
        ai_display_target_fps=settings.vision_ai_display_target_fps,
        require_exact_frame_size=settings.vision_require_exact_frame_size,
        display_crop_left=settings.vision_display_crop_left,
        display_crop_top=settings.vision_display_crop_top,
        display_crop_right=settings.vision_display_crop_right,
        display_crop_bottom=settings.vision_display_crop_bottom,
        polygon_roi_enabled=settings.vision_polygon_roi_enabled,
        polygon_roi_config_path=settings.vision_polygon_roi_config_path,
        board_crop_coordinates=settings.vision_board_crop_coordinates,
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
        publish_evidence=settings.vision_publish_evidence_enabled,
    )
