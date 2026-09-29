"""Deterministic union-mask occupancy calculation for road segmentation."""

from typing import Final

import cv2
import numpy as np

from app.vision.schemas import (
    OccupancyContribution,
    RoadOccupancyResult,
    RoadSegmentationResult,
)


OCCUPANCY_CLASSES: Final = {"ROAD_OBSTACLE", "POTHOLE"}


def calculate_road_occupancy(
    segmentation_result: RoadSegmentationResult,
) -> RoadOccupancyResult:
    """Calculate union-mask occupancy for one road segmentation result."""

    roi = segmentation_result.road_roi
    roi_pixels = roi.width * roi.height
    occupied_mask = np.zeros((roi.height, roi.width), dtype=np.uint8)
    class_masks = {
        class_name: np.zeros((roi.height, roi.width), dtype=np.uint8)
        for class_name in OCCUPANCY_CLASSES
    }
    contributions: list[OccupancyContribution] = []

    for detection_index, detection in enumerate(segmentation_result.segmentations):
        class_name = detection.class_name.upper()
        if class_name not in OCCUPANCY_CLASSES:
            continue
        polygon = np.array(
            [[point.x - roi.x, point.y - roi.y] for point in detection.polygon],
            dtype=np.float32,
        )
        if len(polygon) < 3:
            continue
        polygon_mask = np.zeros((roi.height, roi.width), dtype=np.uint8)
        cv2.fillPoly(polygon_mask, [np.rint(polygon).astype(np.int32)], 1)
        polygon_mask &= 1
        pixels_inside_roi = int(np.count_nonzero(polygon_mask))
        if pixels_inside_roi == 0:
            continue
        occupied_mask |= polygon_mask
        class_masks[class_name] |= polygon_mask
        contributions.append(
            OccupancyContribution(
                detection_index=detection_index,
                class_name=class_name,
                occupied_pixels=pixels_inside_roi,
            )
        )

    occupied_pixels = int(np.count_nonzero(occupied_mask))
    occupancy_ratio = min(1.0, max(0.0, occupied_pixels / roi_pixels))
    class_occupied_pixels = {
        class_name: int(np.count_nonzero(mask))
        for class_name, mask in class_masks.items()
    }
    contributing_classes = [
        class_name
        for class_name in sorted(OCCUPANCY_CLASSES)
        if class_occupied_pixels[class_name] > 0
    ]
    return RoadOccupancyResult(
        road_roi_name=segmentation_result.road_roi_name,
        occupied_pixels=occupied_pixels,
        roi_pixels=roi_pixels,
        occupancy_ratio=occupancy_ratio,
        contributing_detections=contributions,
        contributing_classes=contributing_classes,
        road_obstacle_occupied_pixels=class_occupied_pixels["ROAD_OBSTACLE"],
        pothole_occupied_pixels=class_occupied_pixels["POTHOLE"],
    )
