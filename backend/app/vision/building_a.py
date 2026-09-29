"""Building A object-detection pipeline."""

from datetime import datetime, timezone

from app.vision.capture import CapturedFrame
from app.vision.config import VisionConfig, get_vision_config
from app.vision.detector import YOLODetector
from app.vision.roi import ROIValidationError, crop_frame, validate_roi
from app.vision.schemas import (
    BoundingBox,
    BuildingADetectionResult,
    ROI,
)


class BuildingADetectionError(RuntimeError):
    """Raised when Building A detection cannot be performed."""


class BuildingADetectionPipeline:
    """Crop Building A from a shared frame and run the existing detector."""

    def __init__(
        self,
        detector: YOLODetector | None = None,
        config: VisionConfig | None = None,
    ) -> None:
        self.config = config or get_vision_config()
        self.detector = detector or YOLODetector(config=self.config)

    def process(
        self,
        captured_frame: CapturedFrame,
        building_roi: ROI | None,
    ) -> BuildingADetectionResult:
        """Detect relevant objects in Building A and return full-frame boxes."""

        if building_roi is None:
            raise BuildingADetectionError("Building A ROI is not configured")
        if not self._is_building_a(building_roi):
            raise BuildingADetectionError(
                f"ROI '{building_roi.name}' is not a Building A ROI"
            )
        try:
            validate_roi(
                building_roi,
                frame_width=captured_frame.metadata.width,
                frame_height=captured_frame.metadata.height,
                config=self.config,
            )
            cropped_frame = crop_frame(
                captured_frame.frame,
                building_roi,
                config=self.config,
            )
            detections = self.detector.detect(cropped_frame)
        except ROIValidationError as exc:
            raise BuildingADetectionError(str(exc)) from exc

        translated_detections = [
            detection.model_copy(
                update={
                    "bounding_box": self._to_full_frame_box(
                        detection.bounding_box,
                        building_roi,
                    )
                }
            )
            for detection in detections
        ]
        return BuildingADetectionResult(
            frame=captured_frame.metadata,
            building_roi=building_roi,
            detections=translated_detections,
            processing_timestamp=datetime.now(timezone.utc),
            inference_duration_ms=self.detector.last_inference_duration_ms,
            inference_per_second=self.detector.last_inference_per_second,
        )

    @staticmethod
    def _to_full_frame_box(box: BoundingBox, roi: ROI) -> BoundingBox:
        return BoundingBox(
            x1=box.x1 + roi.x,
            y1=box.y1 + roi.y,
            x2=box.x2 + roi.x,
            y2=box.y2 + roi.y,
        )

    @staticmethod
    def _is_building_a(roi: ROI) -> bool:
        normalized_name = roi.name.strip().lower().replace("-", "_").replace(" ", "_")
        return normalized_name in {"building_a", "buildinga"}
