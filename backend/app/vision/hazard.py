"""Deterministic person-in-hazard-zone geometry evaluation."""

from app.vision.building_a import BuildingADetectionResult
from app.vision.roi import ROIValidationError, validate_roi
from app.vision.schemas import (
    BoundingBox,
    PersonHazardResult,
    ROI,
)


class HazardEvaluationError(ValueError):
    """Raised when a hazard-zone evaluation cannot be performed."""


def evaluate_person_in_hazard(
    detection_result: BuildingADetectionResult,
    hazard_zone: ROI | None,
) -> PersonHazardResult:
    """Evaluate person detections using bounding-box center-point containment."""

    if hazard_zone is None:
        raise HazardEvaluationError("Hazard-zone ROI is not configured")
    normalized_name = hazard_zone.name.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized_name.startswith("hazard"):
        raise HazardEvaluationError(f"ROI '{hazard_zone.name}' is not a hazard-zone ROI")
    try:
        validate_roi(
            hazard_zone,
            frame_width=detection_result.frame.width,
            frame_height=detection_result.frame.height,
        )
    except ROIValidationError as exc:
        raise HazardEvaluationError(str(exc)) from exc

    person_detections = [
        detection
        for detection in detection_result.detections
        if detection.class_name.upper() == "PERSON" and detection.confidence >= 0.50
    ]
    matched_indexes: list[int] = []
    matched_boxes: list[BoundingBox] = []
    for index, detection in enumerate(person_detections):
        if _box_center_inside_roi(detection.bounding_box, hazard_zone):
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
