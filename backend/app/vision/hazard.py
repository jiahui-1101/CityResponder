"""Deterministic person-in-hazard-zone geometry evaluation."""

from app.vision.building_a import BuildingADetectionResult
from app.vision.polygon_roi import point_in_polygon, polygon_area
from app.vision.roi import ROIValidationError, validate_roi
from app.vision.schemas import (
    BoundingBox,
    CoordinateSystem,
    PersonHazardResult,
    PolygonROI,
    ROI,
)


class HazardEvaluationError(ValueError):
    """Raised when a hazard-zone evaluation cannot be performed."""


def evaluate_person_in_hazard(
    detection_result: BuildingADetectionResult,
    hazard_zone: ROI | PolygonROI | None,
) -> PersonHazardResult:
    """Evaluate person detections using bounding-box center-point containment."""

    if hazard_zone is None:
        raise HazardEvaluationError("Hazard-zone ROI is not configured")
    normalized_name = hazard_zone.name.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized_name.startswith("hazard"):
        raise HazardEvaluationError(f"ROI '{hazard_zone.name}' is not a hazard-zone ROI")
    if isinstance(hazard_zone, ROI):
        try:
            validate_roi(
                hazard_zone,
                frame_width=detection_result.frame.width,
                frame_height=detection_result.frame.height,
            )
        except ROIValidationError as exc:
            raise HazardEvaluationError(str(exc)) from exc
    else:
        if hazard_zone.coordinate_system is not CoordinateSystem.RAW_BOARD_CROP:
            raise HazardEvaluationError("Hazard polygon must use RAW_BOARD_CROP coordinates")
        points = [(point.x, point.y) for point in hazard_zone.points]
        if polygon_area(points) <= 0.5:
            raise HazardEvaluationError("Hazard polygon has zero or negligible area")
        if any(
            point.x < 0
            or point.y < 0
            or point.x > detection_result.frame.width
            or point.y > detection_result.frame.height
            for point in hazard_zone.points
        ):
            raise HazardEvaluationError("Hazard polygon falls outside the board frame")

    person_detections = [
        detection
        for detection in detection_result.detections
        if detection.class_name.upper() == "PERSON" and detection.confidence >= 0.50
    ]
    matched_indexes: list[int] = []
    matched_boxes: list[BoundingBox] = []
    for index, detection in enumerate(person_detections):
        center_x = (detection.bounding_box.x1 + detection.bounding_box.x2) / 2
        center_y = (detection.bounding_box.y1 + detection.bounding_box.y2) / 2
        if (
            _box_center_inside_roi(detection.bounding_box, hazard_zone)
            if isinstance(hazard_zone, ROI)
            else point_in_polygon((center_x, center_y), [(point.x, point.y) for point in hazard_zone.points])
        ):
            matched_indexes.append(index)
            matched_boxes.append(detection.bounding_box)

    return PersonHazardResult(
        frame=detection_result.frame,
        hazard_zone=hazard_zone,
        person_detections=person_detections,
        person_in_hazard=bool(matched_indexes),
        matched_person_indexes=matched_indexes,
        matched_person_bounding_boxes=matched_boxes,
    )


def _box_center_inside_roi(box: BoundingBox, roi: ROI) -> bool:
    """Return true when a detection box center is within the ROI bounds."""

    center_x = (box.x1 + box.x2) / 2
    center_y = (box.y1 + box.y2) / 2
    return (
        roi.x <= center_x <= roi.x + roi.width
        and roi.y <= center_y <= roi.y + roi.height
    )
