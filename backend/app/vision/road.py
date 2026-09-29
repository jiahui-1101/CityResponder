"""Multi-ROI road segmentation pipeline."""

from datetime import datetime, timezone

from app.vision.capture import CapturedFrame
from app.vision.config import VisionConfig, get_vision_config
from app.vision.roi import ROIValidationError, crop_frame, validate_roi
from app.vision.schemas import (
    BoundingBox,
    PolygonPoint,
    ROI,
    RoadSegmentationResult,
    SegmentationDetection,
)
from app.vision.segmentation import YOLOSegmentation


class RoadSegmentationError(RuntimeError):
    """Raised when road segmentation cannot be performed."""


class RoadSegmentationPipeline:
    """Run the shared segmentation service for one or more road ROIs."""

    def __init__(
        self,
        segmenter: YOLOSegmentation | None = None,
        config: VisionConfig | None = None,
    ) -> None:
        self.config = config or get_vision_config()
        self.segmenter = segmenter or YOLOSegmentation(config=self.config)

    def process(
        self,
        captured_frame: CapturedFrame,
        road_rois: list[ROI],
    ) -> list[RoadSegmentationResult]:
        """Segment each configured road ROI using the shared captured frame."""

        if not road_rois:
            raise RoadSegmentationError("No road ROIs are configured")

        results: list[RoadSegmentationResult] = []
        for road_roi in road_rois:
            if not self._is_road(road_roi):
                raise RoadSegmentationError(
                    f"ROI '{road_roi.name}' is not a road ROI"
                )
            try:
                validate_roi(
                    road_roi,
                    frame_width=captured_frame.metadata.width,
                    frame_height=captured_frame.metadata.height,
                    config=self.config,
                )
                cropped_frame = crop_frame(
                    captured_frame.frame,
                    road_roi,
                    config=self.config,
                )
                segmentations = self.segmenter.segment(cropped_frame)
            except ROIValidationError as exc:
                raise RoadSegmentationError(str(exc)) from exc

            results.append(
                RoadSegmentationResult(
                    frame=captured_frame.metadata,
                    road_roi_name=road_roi.name,
                    road_roi=road_roi,
                    segmentations=[
                        self._to_full_frame_coordinates(segmentation, road_roi)
                        for segmentation in segmentations
                    ],
                    processing_timestamp=datetime.now(timezone.utc),
                    inference_duration_ms=self.segmenter.last_inference_duration_ms,
                    inference_per_second=self.segmenter.last_inference_per_second,
                )
            )
        return results

    @staticmethod
    def _to_full_frame_coordinates(
        segmentation: SegmentationDetection,
        roi: ROI,
    ) -> SegmentationDetection:
        translated_box = BoundingBox(
            x1=segmentation.bounding_box.x1 + roi.x,
            y1=segmentation.bounding_box.y1 + roi.y,
            x2=segmentation.bounding_box.x2 + roi.x,
            y2=segmentation.bounding_box.y2 + roi.y,
        )
        translated_polygon = [
            PolygonPoint(x=point.x + roi.x, y=point.y + roi.y)
            for point in segmentation.polygon
        ]
        return segmentation.model_copy(
            update={
                "bounding_box": translated_box,
                "polygon": translated_polygon,
            }
        )

    @staticmethod
    def _is_road(roi: ROI) -> bool:
        normalized_name = roi.name.strip().lower().replace("-", "_").replace(" ", "_")
        return normalized_name.startswith("road")
