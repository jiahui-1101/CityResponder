"""Deterministic spatial evidence derived from road segmentation results."""

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import (
    ObstacleSpatialEvidence,
    RoadSegmentationResult,
    RoadSpatialEvidenceResult,
)


def calculate_road_spatial_evidence(
    segmentation_result: RoadSegmentationResult,
    config: VisionConfig | None = None,
) -> RoadSpatialEvidenceResult:
    """Measure ROAD_OBSTACLE extents without interpreting routing semantics."""

    vision_config = config or get_vision_config()
    contributions: list[ObstacleSpatialEvidence] = []
    for detection_index, detection in enumerate(segmentation_result.segmentations):
        if detection.class_name.upper() != "ROAD_OBSTACLE":
            continue
        box = detection.bounding_box
        bounding_width = abs(box.x2 - box.x1)
        bounding_height = abs(box.y2 - box.y1)
        x_values = [point.x for point in detection.polygon]
        y_values = [point.y for point in detection.polygon]
        polygon_span_x = max(x_values) - min(x_values)
        polygon_span_y = max(y_values) - min(y_values)
        max_extent = max(
            bounding_width,
            bounding_height,
            polygon_span_x,
            polygon_span_y,
        )
        extent_cm = (
            max_extent * vision_config.pixel_to_cm_scale
            if vision_config.pixel_to_cm_scale is not None
            else None
        )
        contributions.append(
            ObstacleSpatialEvidence(
                detection_index=detection_index,
                class_name="ROAD_OBSTACLE",
                bounding_width_px=bounding_width,
                bounding_height_px=bounding_height,
                polygon_span_x_px=polygon_span_x,
                polygon_span_y_px=polygon_span_y,
                max_extent_px=max_extent,
                max_extent_cm=extent_cm,
            )
        )

    obstacle_extents_px = [item.max_extent_px for item in contributions]
    obstacle_extents_cm = [item.max_extent_cm for item in contributions]
    max_obstacle_extent_px = max(obstacle_extents_px, default=0.0)
    configured_cm_extents = [value for value in obstacle_extents_cm if value is not None]
    max_obstacle_extent_cm = max(configured_cm_extents, default=None)
    return RoadSpatialEvidenceResult(
        road_roi_name=segmentation_result.road_roi_name,
        obstacle_count=len(contributions),
        max_obstacle_extent_px=max_obstacle_extent_px,
        obstacle_extents_px=obstacle_extents_px,
        max_obstacle_extent_cm=max_obstacle_extent_cm,
        obstacle_extents_cm=obstacle_extents_cm,
        contributing_detections=contributions,
    )
