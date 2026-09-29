"""Lazy YOLO object-detection wrapper for relevant CityResponder labels."""

import logging
from time import perf_counter
from typing import Any

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import BoundingBox, Detection


logger = logging.getLogger(__name__)
RELEVANT_LABELS = {"FIRE", "SMOKE", "PERSON"}


class DetectorError(RuntimeError):
    """Base error for controlled detector setup and inference failures."""


class DetectorLoadError(DetectorError):
    """Raised when the configured YOLO model cannot be loaded."""


class DetectorInferenceError(DetectorError):
    """Raised when YOLO inference cannot process a frame."""


class YOLODetector:
    """Lazily load and run the configured YOLO detection model."""

    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or get_vision_config()
        self._model: Any | None = None
        self.last_inference_duration_ms: float | None = None
        self.last_inference_per_second: float | None = None

    def detect(self, frame: Any) -> list[Detection]:
        """Run inference on an in-memory OpenCV frame."""

        if frame is None:
            raise DetectorInferenceError("Cannot run detection on an empty frame")
        model = self._load_model()
        try:
            predict_kwargs: dict[str, Any] = {"source": frame, "verbose": False}
            if self.config.detection_confidence_threshold is not None:
                predict_kwargs["conf"] = self.config.detection_confidence_threshold
            started_at = perf_counter()
            results = model.predict(**predict_kwargs)
            duration_seconds = perf_counter() - started_at
            self.last_inference_duration_ms = duration_seconds * 1000
            self.last_inference_per_second = (
                1 / duration_seconds if duration_seconds > 0 else None
            )
            return self._parse_results(results)
        except DetectorError:
            raise
        except Exception as exc:
            logger.exception("YOLO detection failed")
            raise DetectorInferenceError("YOLO detection failed") from exc

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.config.detection_model)
            return self._model
        except Exception as exc:
            logger.exception("Unable to load YOLO detection model")
            raise DetectorLoadError(
                f"Unable to load YOLO detection model: {self.config.detection_model}"
            ) from exc

    def _parse_results(self, results: Any) -> list[Detection]:
        detections: list[Detection] = []
        try:
            for result in results:
                boxes = result.boxes
                names = getattr(result, "names", {})
                for box, confidence, class_index in zip(
                    boxes.xyxy,
                    boxes.conf,
                    boxes.cls,
                ):
                    score = float(confidence.item())
                    if (
                        self.config.detection_confidence_threshold is not None
                        and score < self.config.detection_confidence_threshold
                    ):
                        continue
                    label = self._label_for(names, int(class_index.item()))
                    normalized_label = label.strip().upper()
                    if normalized_label not in RELEVANT_LABELS:
                        continue
                    coordinates = [float(value) for value in box.tolist()]
                    detections.append(
                        Detection(
                            class_name=normalized_label,
                            confidence=score,
                            bounding_box=BoundingBox(
                                x1=coordinates[0],
                                y1=coordinates[1],
                                x2=coordinates[2],
                                y2=coordinates[3],
                            ),
                        )
                    )
            return detections
        except Exception as exc:
            logger.exception("Unable to parse YOLO detection results")
            raise DetectorInferenceError("Unable to parse YOLO detection results") from exc

    @staticmethod
    def _label_for(names: Any, class_index: int) -> str:
        if isinstance(names, dict):
            return str(names[class_index])
        return str(names[class_index])
