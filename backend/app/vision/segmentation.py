"""Lazy YOLO segmentation wrapper for relevant CityResponder labels."""

import logging
from time import perf_counter
from typing import Any

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import (
    BoundingBox,
    PolygonPoint,
    SegmentationDetection,
)


logger = logging.getLogger(__name__)
RELEVANT_LABELS = {"ROAD_OBSTACLE", "POTHOLE"}


class SegmentationError(RuntimeError):
    """Base error for controlled segmentation setup and inference failures."""


class SegmentationLoadError(SegmentationError):
    """Raised when the configured segmentation model cannot be loaded."""


class SegmentationInferenceError(SegmentationError):
    """Raised when segmentation inference or result parsing fails."""


class YOLOSegmentation:
    """Lazily load and run the configured YOLO segmentation model."""

    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or get_vision_config()
        self._model: Any | None = None
        self.last_inference_duration_ms: float | None = None
        self.last_inference_per_second: float | None = None

    def segment(self, frame: Any) -> list[SegmentationDetection]:
        """Run segmentation on an in-memory OpenCV frame."""

        if frame is None:
            raise SegmentationInferenceError("Cannot run segmentation on an empty frame")
        model = self._load_model()
        try:
            predict_kwargs: dict[str, Any] = {"source": frame, "verbose": False}
            if self.config.segmentation_confidence_threshold is not None:
                predict_kwargs["conf"] = self.config.segmentation_confidence_threshold
            started_at = perf_counter()
            results = model.predict(**predict_kwargs)
            duration_seconds = perf_counter() - started_at
            self.last_inference_duration_ms = duration_seconds * 1000
            self.last_inference_per_second = (
                1 / duration_seconds if duration_seconds > 0 else None
            )
            return self._parse_results(results)
        except SegmentationError:
            raise
        except Exception as exc:
            logger.exception("YOLO segmentation failed")
            raise SegmentationInferenceError("YOLO segmentation failed") from exc

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.config.segmentation_model)
            return self._model
        except Exception as exc:
            logger.exception("Unable to load YOLO segmentation model")
            raise SegmentationLoadError(
                f"Unable to load YOLO segmentation model: "
                f"{self.config.segmentation_model}"
            ) from exc

    def _parse_results(self, results: Any) -> list[SegmentationDetection]:
        segmentations: list[SegmentationDetection] = []
        try:
            for result in results:
                boxes = result.boxes
                masks = getattr(result, "masks", None)
                if masks is None:
                    continue
                names = getattr(result, "names", {})
                polygons = masks.xy
                for index, (box, confidence, class_index) in enumerate(
                    zip(boxes.xyxy, boxes.conf, boxes.cls)
                ):
                    if index >= len(polygons):
                        continue
                    score = float(confidence.item())
                    if (
                        self.config.segmentation_confidence_threshold is not None
                        and score < self.config.segmentation_confidence_threshold
                    ):
                        continue
                    label = self._label_for(names, int(class_index.item()))
                    normalized_label = label.strip().upper()
                    if normalized_label not in RELEVANT_LABELS:
                        continue
                    coordinates = [float(value) for value in box.tolist()]
                    polygon = [
                        PolygonPoint(x=float(point[0]), y=float(point[1]))
                        for point in polygons[index]
                    ]
                    if not polygon:
                        continue
                    segmentations.append(
                        SegmentationDetection(
                            class_name=normalized_label,
                            confidence=score,
                            bounding_box=BoundingBox(
                                x1=coordinates[0],
                                y1=coordinates[1],
                                x2=coordinates[2],
                                y2=coordinates[3],
                            ),
                            polygon=polygon,
                        )
                    )
            return segmentations
        except Exception as exc:
            logger.exception("Unable to parse YOLO segmentation results")
            raise SegmentationInferenceError(
                "Unable to parse YOLO segmentation results"
            ) from exc

    @staticmethod
    def _label_for(names: Any, class_index: int) -> str:
        if isinstance(names, dict):
            return str(names[class_index])
        return str(names[class_index])
