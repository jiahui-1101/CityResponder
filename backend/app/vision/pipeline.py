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
from app.vision.publisher import VisionEvidencePublisher, vision_evidence_publisher
from app.vision.roi import ROIValidationError, crop_frame, get_configured_rois, validate_roi
from app.vision.runtime import vision_runtime_health
from app.vision.schemas import (
    BuildingADetectionResult,
    CoordinateSystem,
    Detection,
    FrameMetadata,
    FrozenModelIdentity,
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
                self.publisher.publish_detection(processed.detection_result)
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
        rois = get_configured_rois(self.config)
        board_roi = self._require_one(rois["board"], "board crop")
        building_roi = self._require_one(rois["building_a"], "Building A ROI")
        road_rois = rois["road"]
        if not road_rois:
            raise VisionIntegrationError("At least one road ROI is required")

        crop_started = perf_counter()
        try:
            board_frame = crop_frame(captured.frame, board_roi, config=self.config)
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
            if _box_center_inside_roi(detection, building_roi)
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
        )

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
        for detection in processed.result.detections:
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
        for segmentation in processed.result.segmentations:
            polygon = np.asarray(
                [[round(point.x), round(point.y)] for point in segmentation.polygon],
                dtype=np.int32,
            )
            cv2.polylines(
                frame,
                [polygon],
                True,
                (255, 0, 0),
                2,
            )
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
