"""Shared-frame integration of the frozen detection and segmentation models."""

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from app.vision.capture import CapturedFrame, VisionCaptureService
from app.vision.config import VisionConfig, get_vision_config
from app.vision.detector import YOLODetector
from app.vision.evidence import RoadVisionEvidenceService
from app.vision.hazard import evaluate_person_in_hazard
from app.vision.occupancy import calculate_road_occupancy
from app.vision.polygon_roi import (
    PolygonROIConfigError,
    PolygonROIConfiguration,
    RoadRegionMask,
    load_polygon_roi_config,
    point_in_polygon,
)
from app.vision.publisher import VisionEvidencePublisher, vision_evidence_publisher
from app.vision.roi import ROIValidationError, crop_frame, get_configured_rois, validate_roi
from app.vision.runtime import vision_runtime_health
from app.vision.schemas import (
    BuildingADetectionResult,
    CoordinateSystem,
    Detection,
    FrameMetadata,
    FrozenModelIdentity,
    PersonHazardResult,
    PolygonROI,
    ROI,
    RoadSegmentationResult,
    RoadVisionEvidence,
    SegmentationDetection,
    UnifiedVisionResult,
)
from app.vision.segmentation import YOLOSegmentation
from app.vision.spatial import calculate_road_spatial_evidence


DETECTION_VERSION = "cityresponder_detection_v2"
SEGMENTATION_VERSION = "cityresponder_segmentation_v1"


class VisionIntegrationError(RuntimeError):
    """Raised when a frame cannot produce trustworthy integrated evidence."""


@dataclass(frozen=True)
class ProcessedVisionFrame:
    """In-memory products from one shared frame; nothing is persisted here."""

    board_frame: Any
    result: UnifiedVisionResult
    detection_result: BuildingADetectionResult
    road_evidence: list[RoadVisionEvidence]
    person_hazard: PersonHazardResult | None = None
    polygon_roi_config: PolygonROIConfiguration | None = None


class IntegratedVisionPipeline:
    """Capture once, crop once, run both frozen models, then publish evidence."""

    def __init__(
        self,
        *,
        config: VisionConfig | None = None,
        capture: VisionCaptureService | None = None,
        detector: YOLODetector | None = None,
        segmenter: YOLOSegmentation | None = None,
        publisher: VisionEvidencePublisher | None = None,
    ) -> None:
        self.config = config or get_vision_config()
        self.polygon_roi_config: PolygonROIConfiguration | None = None
        if self.config.polygon_roi_enabled:
            try:
                self.polygon_roi_config = load_polygon_roi_config(
                    self.config.polygon_roi_config_path,
                    expected_resolution=(self.config.frame_width, self.config.frame_height),
                )
            except PolygonROIConfigError as exc:
                raise VisionIntegrationError(f"Invalid opt-in polygon ROI config: {exc}") from exc
        self.capture = capture or VisionCaptureService(config=self.config)
        self.detector = detector or YOLODetector(config=self.config)
        self.segmenter = segmenter or YOLOSegmentation(config=self.config)
        self.publisher = publisher or vision_evidence_publisher

    def process_one(self, *, publish: bool = True) -> ProcessedVisionFrame:
        """Process one real/shared frame; failures never become empty safe evidence."""

        started_at = perf_counter()
        try:
            capture_started = perf_counter()
            captured = self.capture.capture_one()
            capture_duration_ms = (perf_counter() - capture_started) * 1000
            if captured is None:
                raise VisionIntegrationError("Configured vision source returned no frame")
            processed = self.process_captured_frame(
                captured,
                capture_duration_ms=capture_duration_ms,
                total_started_at=started_at,
            )
            if publish:
                self.publisher.publish_detection(
                    processed.detection_result,
                    processed.person_hazard,
                )
                for evidence in processed.road_evidence:
                    self.publisher.publish_road(evidence)
            vision_runtime_health.success(processed.result.frame.frame_id)
            return processed
        except Exception as exc:
            vision_runtime_health.failure(f"Integrated vision failure: {exc}")
            if isinstance(exc, VisionIntegrationError):
                raise
            raise VisionIntegrationError(f"Integrated vision failure: {exc}") from exc

    def process_captured_frame(
        self,
        captured: CapturedFrame,
        *,
        capture_duration_ms: float = 0.0,
        total_started_at: float | None = None,
    ) -> ProcessedVisionFrame:
        """Process a supplied frame for deterministic tests and shared-source use."""

        total_started = total_started_at or perf_counter()
        polygon_config = self.polygon_roi_config
        road_masks: list[RoadRegionMask] = []
        if polygon_config is None:
            rois = get_configured_rois(self.config)
            board_roi = self._require_one(rois["board"], "board crop")
            building_roi = self._require_one(rois["building_a"], "Building A ROI")
            road_rois = rois["road"]
            if not road_rois:
                raise VisionIntegrationError("At least one road ROI is required")
            building_polygon = None
            hazard_polygon = None
            hazard_zone = None
        else:
            board_roi = polygon_config.crop
            building_roi = polygon_config.building.bounding_roi()
            road_masks = polygon_config.road_masks(
                (board_roi.height, board_roi.width, 3)
            )
            road_rois = [mask.roi for mask in road_masks]
            building_polygon = polygon_config.building.as_polygon_roi()
            hazard_polygon = polygon_config.hazard.as_polygon_roi()
            hazard_zone = hazard_polygon

        crop_started = perf_counter()
        try:
            board_frame = crop_frame(captured.frame, board_roi, config=self.config)
            if polygon_config is None:
                validate_roi(
                    building_roi,
                    frame_width=board_roi.width,
                    frame_height=board_roi.height,
                    config=self.config,
                )
                for road_roi in road_rois:
                    validate_roi(
                        road_roi,
                        frame_width=board_roi.width,
                        frame_height=board_roi.height,
                        config=self.config,
                    )
        except ROIValidationError as exc:
            raise VisionIntegrationError(str(exc)) from exc
        crop_duration_ms = (perf_counter() - crop_started) * 1000

        board_metadata = FrameMetadata(
            frame_id=f"{captured.metadata.frame_id}:board",
            timestamp=captured.metadata.timestamp,
            source=captured.metadata.source,
            width=board_roi.width,
            height=board_roi.height,
            coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
            parent_frame_id=captured.metadata.frame_id,
            crop_origin_x=board_roi.x,
            crop_origin_y=board_roi.y,
        )

        detection_started = perf_counter()
        detections = self.detector.detect(board_frame)
        detection_duration_ms = (perf_counter() - detection_started) * 1000
        segmentation_started = perf_counter()
        segmentations = self.segmenter.segment(board_frame)
        segmentation_duration_ms = (perf_counter() - segmentation_started) * 1000

        post_started = perf_counter()
        building_detections = [
            detection
            for detection in detections
            if (
                _box_center_inside_roi(detection, building_roi)
                if building_polygon is None
                else _box_center_inside_polygon(detection, building_polygon)
            )
        ]
        detection_model = self._detection_identity()
        segmentation_model = self._segmentation_identity()
        detection_result = BuildingADetectionResult(
            frame=board_metadata,
            building_roi=building_roi,
            detections=building_detections,
            processing_timestamp=datetime.now(timezone.utc),
            inference_duration_ms=self.detector.last_inference_duration_ms,
            inference_per_second=self.detector.last_inference_per_second,
            board_crop=board_roi,
            model=detection_model,
            building_polygon=building_polygon,
            hazard_polygon=hazard_polygon,
        )
        person_hazard = (
            evaluate_person_in_hazard(detection_result, hazard_zone)
            if hazard_zone is not None
            else None
        )
        if person_hazard is not None:
            detection_result = detection_result.model_copy(
                update={"person_in_hazard": person_hazard.person_in_hazard}
            )

        if polygon_config is None:
            road_segmentations = [
                RoadSegmentationResult(
                    frame=board_metadata,
                    road_roi_name=road_roi.name,
                    road_roi=road_roi,
                    segmentations=[
                        item for item in segmentations if _segmentation_intersects_roi(item, road_roi)
                    ],
                    processing_timestamp=datetime.now(timezone.utc),
                    inference_duration_ms=self.segmenter.last_inference_duration_ms,
                    inference_per_second=self.segmenter.last_inference_per_second,
                )
                for road_roi in road_rois
            ]
        else:
            road_segmentations = [
                RoadSegmentationResult(
                    frame=board_metadata,
                    road_roi_name=mask.region.label,
                    road_roi=mask.roi,
                    segmentations=[
                        item
                        for item in segmentations
                        if _segmentation_intersects_mask(item, mask.roi, mask.valid_mask)
                    ],
                    processing_timestamp=datetime.now(timezone.utc),
                    inference_duration_ms=self.segmenter.last_inference_duration_ms,
                    inference_per_second=self.segmenter.last_inference_per_second,
                    road_polygon=mask.region.as_polygon_roi(),
                    valid_road_mask=mask.valid_mask,
                )
                for mask in road_masks
            ]
        occupancies = [calculate_road_occupancy(item) for item in road_segmentations]
        spatial = [calculate_road_spatial_evidence(item, self.config) for item in road_segmentations]
        road_evidence = [
            item.model_copy(
                update={"board_crop": board_roi, "model": segmentation_model}
            )
            for item in RoadVisionEvidenceService().combine(
                road_segmentations,
                occupancies,
                spatial,
            )
        ]
        postprocessing_duration_ms = (perf_counter() - post_started) * 1000
        total_duration_ms = (perf_counter() - total_started) * 1000
        result = UnifiedVisionResult(
            raw_frame=captured.metadata,
            frame=board_metadata,
            board_crop=board_roi,
            building_roi=building_roi,
            road_rois=road_rois,
            building_polygon=building_polygon,
            hazard_polygon=hazard_polygon,
            road_polygons=[mask.region.as_polygon_roi() for mask in road_masks],
            detections=detections,
            segmentations=segmentations,
            detection_model=detection_model,
            segmentation_model=segmentation_model,
            processing_timestamp=datetime.now(timezone.utc),
            capture_duration_ms=capture_duration_ms,
            crop_duration_ms=crop_duration_ms,
            detection_duration_ms=detection_duration_ms,
            segmentation_duration_ms=segmentation_duration_ms,
            postprocessing_duration_ms=postprocessing_duration_ms,
            total_duration_ms=total_duration_ms,
        )
        return ProcessedVisionFrame(
            board_frame=board_frame,
            result=result,
            detection_result=detection_result,
            road_evidence=road_evidence,
            person_hazard=person_hazard,
            polygon_roi_config=polygon_config,
        )

    def close(self) -> None:
        self.capture.close()

    def render_annotated_frame(
        self,
        processed: ProcessedVisionFrame,
    ) -> tuple[bytes, dict[str, Any]]:
        """Render one caller-selected frame; this method never stores video or images."""

        frame = processed.board_frame.copy()
        building = processed.result.building_roi
        if processed.result.building_polygon is not None:
            if processed.polygon_roi_config is not None:
                overlay = frame.copy()
                for exclusion in processed.polygon_roi_config.exclusions:
                    points = np.rint(exclusion.board_points).astype(np.int32)
                    cv2.fillPoly(overlay, [points], (120, 120, 120))
                cv2.addWeighted(overlay, 0.24, frame, 0.76, 0, frame)
                colors = ((255, 170, 0), (255, 0, 255), (0, 165, 255))
                for index, region in enumerate(processed.polygon_roi_config.road_segments):
                    _draw_polygon(
                        frame,
                        region.as_polygon_roi(),
                        colors[index % len(colors)],
                        2,
                    )
                crop_origin = (
                    processed.result.board_crop.x,
                    processed.result.board_crop.y,
                )
                for index, raw_points in enumerate(
                    processed.polygon_roi_config.junction_raw_regions,
                    start=1,
                ):
                    board_points = np.rint(
                        [
                            (point[0] - crop_origin[0], point[1] - crop_origin[1])
                            for point in raw_points
                        ]
                    ).astype(np.int32)
                    cv2.polylines(
                        frame,
                        [board_points],
                        True,
                        (40, 220, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        frame,
                        f"J{index}",
                        tuple(board_points[0]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.48,
                        (40, 220, 255),
                        1,
                        cv2.LINE_AA,
                    )
            _draw_polygon(frame, processed.result.building_polygon, (0, 200, 120), 2)
            _draw_polygon(frame, processed.result.hazard_polygon, (0, 200, 255), 2)
        else:
            cv2.rectangle(
                frame,
                (round(building.x), round(building.y)),
                (round(building.x + building.width), round(building.y + building.height)),
                (0, 200, 120),
                2,
            )
            cv2.putText(
                frame,
                "BUILDING A ROI",
                (round(building.x), max(18, round(building.y) - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 200, 120),
                2,
                cv2.LINE_AA,
            )
        detections_to_draw = processed.result.detections
        if processed.polygon_roi_config is not None:
            detections_to_draw = processed.detection_result.detections
        for detection in detections_to_draw:
            box = detection.bounding_box
            cv2.rectangle(
                frame,
                (round(box.x1), round(box.y1)),
                (round(box.x2), round(box.y2)),
                (0, 0, 255),
                2,
            )
            cv2.putText(
                frame,
                f"{detection.class_name} {detection.confidence:.2f}",
                (round(box.x1), max(18, round(box.y1) - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )
        if processed.polygon_roi_config is not None:
            masks = processed.polygon_roi_config.road_masks(processed.board_frame.shape)
            for segmentation in processed.result.segmentations:
                for mask in masks:
                    contours = _segmentation_contours_in_mask(
                        segmentation,
                        mask.roi,
                        mask.valid_mask,
                    )
                    if not contours:
                        continue
                    cv2.drawContours(frame, contours, -1, (255, 0, 0), 2)
                    x, y, _width, _height = cv2.boundingRect(contours[0])
                    cv2.putText(
                        frame,
                        f"{segmentation.class_name} {segmentation.confidence:.2f}",
                        (x, max(18, y - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 0, 0),
                        1,
                        cv2.LINE_AA,
                    )
        else:
            for segmentation in processed.result.segmentations:
                polygon = np.asarray(
                    [[round(point.x), round(point.y)] for point in segmentation.polygon],
                    dtype=np.int32,
                )
                cv2.polylines(frame, [polygon], True, (255, 0, 0), 2)
                if len(polygon):
                    cv2.putText(
                        frame,
                        f"{segmentation.class_name} {segmentation.confidence:.2f}",
                        tuple(polygon[0]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 0, 0),
                        1,
                        cv2.LINE_AA,
                    )
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise VisionIntegrationError("Unable to encode annotated evidence frame")
        metadata = {
            "frame_id": processed.result.frame.frame_id,
            "timestamp": processed.result.frame.timestamp.isoformat(),
            "coordinate_system": CoordinateSystem.RAW_BOARD_CROP.value,
            "detections": [item.model_dump(mode="json") for item in processed.result.detections],
            "segmentations": [
                item.model_dump(mode="json") for item in processed.result.segmentations
            ],
            "detection_model": processed.result.detection_model.model_dump(mode="json"),
            "segmentation_model": processed.result.segmentation_model.model_dump(mode="json"),
            "person_in_hazard": processed.detection_result.person_in_hazard,
            "building_polygon": (
                processed.result.building_polygon.model_dump(mode="json")
                if processed.result.building_polygon is not None
                else None
            ),
            "hazard_polygon": (
                processed.result.hazard_polygon.model_dump(mode="json")
                if processed.result.hazard_polygon is not None
                else None
            ),
            "road_polygons": [
                polygon.model_dump(mode="json")
                for polygon in processed.result.road_polygons
            ],
        }
        return encoded.tobytes(), metadata

    def _detection_identity(self) -> FrozenModelIdentity:
        return FrozenModelIdentity(
            name="YOLOv8n detection",
            version=DETECTION_VERSION,
            task="detect",
            weights=self.config.detection_model,
            classes=["fire", "smoke", "person"],
        )

    def _segmentation_identity(self) -> FrozenModelIdentity:
        return FrozenModelIdentity(
            name="YOLOv8n-seg",
            version=SEGMENTATION_VERSION,
            task="segment",
            weights=self.config.segmentation_model,
            classes=["road_obstacle", "pothole"],
        )

    @staticmethod
    def _require_one(items: list[ROI], label: str) -> ROI:
        if len(items) != 1:
            raise VisionIntegrationError(
                f"Exactly one {label} is required; configured count={len(items)}"
            )
        return items[0]


def _box_center_inside_roi(detection: Detection, roi: ROI) -> bool:
    box = detection.bounding_box
    center_x = (box.x1 + box.x2) / 2
    center_y = (box.y1 + box.y2) / 2
    return (
        roi.x <= center_x <= roi.x + roi.width
        and roi.y <= center_y <= roi.y + roi.height
    )


def _segmentation_intersects_roi(item: SegmentationDetection, roi: ROI) -> bool:
    box = item.bounding_box
    return not (
        box.x2 < roi.x
        or box.x1 > roi.x + roi.width
        or box.y2 < roi.y
        or box.y1 > roi.y + roi.height
    )


def _box_center_inside_polygon(detection: Detection, polygon: PolygonROI) -> bool:
    box = detection.bounding_box
    center = ((box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2)
    return point_in_polygon(
        center,
        [(point.x, point.y) for point in polygon.points],
    )


def _segmentation_intersects_mask(
    item: SegmentationDetection,
    roi: ROI,
    valid_mask: np.ndarray,
) -> bool:
    """Return whether any segmentation polygon pixel falls on valid road."""

    return bool(_segmentation_contours_in_mask(item, roi, valid_mask))


def _segmentation_contours_in_mask(
    item: SegmentationDetection,
    roi: ROI,
    valid_mask: np.ndarray,
) -> list[np.ndarray]:
    if len(item.polygon) < 3:
        return []
    points = np.asarray([[point.x, point.y] for point in item.polygon], dtype=np.float64)
    mask_height, mask_width = valid_mask.shape[:2]
    x1 = max(roi.x, 0, int(np.floor(points[:, 0].min())))
    y1 = max(roi.y, 0, int(np.floor(points[:, 1].min())))
    x2 = min(roi.x + roi.width, mask_width, int(np.ceil(points[:, 0].max())) + 1)
    y2 = min(roi.y + roi.height, mask_height, int(np.ceil(points[:, 1].max())) + 1)
    if x2 <= x1 or y2 <= y1:
        return []
    local_mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    local_points = np.rint(points - np.array([x1, y1])).astype(np.int32)
    cv2.fillPoly(local_mask, [local_points], 1)
    local_mask[valid_mask[y1:y2, x1:x2] == 0] = 0
    contours, _hierarchy = cv2.findContours(
        local_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    for contour in contours:
        contour[:, 0, 0] += x1
        contour[:, 0, 1] += y1
    return contours


def _draw_polygon(
    frame: np.ndarray,
    polygon: PolygonROI | None,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    if polygon is None:
        return
    points = np.rint([[point.x, point.y] for point in polygon.points]).astype(np.int32)
    cv2.polylines(frame, [points], True, color, thickness, cv2.LINE_AA)
    anchor = points[0]
    cv2.putText(
        frame,
        polygon.name,
        (int(anchor[0]), max(18, int(anchor[1]) - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        color,
        1,
        cv2.LINE_AA,
    )
