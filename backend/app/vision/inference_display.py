"""Observation-only YOLO output tied to the shared physical camera frames."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Condition, Event, Thread
from time import monotonic, perf_counter
from typing import Any, Callable

import cv2
import numpy as np

from app.vision.config import VisionConfig, get_vision_config
from app.vision.device import resolve_inference_device
from app.vision.detector import YOLODetector
from app.vision.preview import (
    JPEG_QUALITY,
    MAX_JPEG_BYTES,
    PREVIEW_HEIGHT,
    PREVIEW_WIDTH,
    CameraPreviewUnavailable,
    SharedCameraPreviewService,
    shared_camera_preview,
)
from app.vision.schemas import CoordinateSystem, Detection, SegmentationDetection


logger = logging.getLogger(__name__)
IDLE_TIMEOUT_SECONDS = 20.0
MAX_INFERENCE_FPS = 5.0
INFERENCE_FRESH_SECONDS = 2.0
MAX_RESULT_BYTES = 1_000_000
CLASS_COLORS = {
    "FIRE": (0, 0, 255),
    "SMOKE": (180, 180, 180),
    "PERSON": (0, 210, 80),
    "ROAD_OBSTACLE": (0, 80, 255),
    "POTHOLE": (0, 190, 255),
}


@dataclass(frozen=True)
class VisionDisplayFrame:
    """Annotated JPEG plus exact source-frame identity and fresh predictions."""

    jpeg: bytes
    frame_id: str
    timestamp: datetime
    processed_at: datetime
    capture_width: int
    capture_height: int
    preview_width: int
    preview_height: int
    sequence: int
    detections: tuple[dict[str, Any], ...]
    segmentations: tuple[dict[str, Any], ...]
    detection_status: str
    segmentation_status: str
    detection_fps: float
    segmentation_fps: float
    detection_latency_ms: float | None
    segmentation_latency_ms: float | None
    inference_latency_ms: float
    camera_fps: float
    inference_device: str
    source_width: int | None = None
    source_height: int | None = None
    crop_origin_x: int = 0
    crop_origin_y: int = 0
    crop_right_x: int | None = None
    crop_bottom_y: int | None = None


class VisionDisplayUnavailable(RuntimeError):
    """No completed observation-only inference frame is available."""


@dataclass
class AIFramePresentationPolicy:
    """Bounded display-only lifecycle for synchronized composited AI frames."""

    valid_seconds: float
    last_ai_sequence: int = -1
    last_frame_id: str | None = None
    last_timestamp: datetime | None = None
    geometry_version: str | None = None

    @property
    def has_ai_frame(self) -> bool:
        return self.last_ai_sequence >= 0

    def allow_raw_fallback(self) -> bool:
        return not self.has_ai_frame

    def accept_ai(
        self,
        *,
        sequence: int,
        frame_id: str,
        timestamp: datetime,
        geometry_version: str,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(timezone.utc)
        age = max(0.0, (current - timestamp).total_seconds())
        if sequence <= self.last_ai_sequence or age > self.valid_seconds:
            return False
        self.last_ai_sequence = sequence
        self.last_frame_id = frame_id
        self.last_timestamp = timestamp
        self.geometry_version = geometry_version
        return True

    def overlay_state(self, now: datetime | None = None) -> str:
        if self.last_timestamp is None:
            return "warming"
        current = now or datetime.now(timezone.utc)
        age = max(0.0, (current - self.last_timestamp).total_seconds())
        return "stale" if age > self.valid_seconds else "processing"


class SharedVisionDisplayService:
    """Run the frozen detector and segmenter on frames from one camera owner."""

    def __init__(
        self,
        camera: SharedCameraPreviewService | None = None,
        *,
        config: VisionConfig | None = None,
        detector_factory: Callable[[VisionConfig], Any] = YOLODetector,
        segmenter_factory: Callable[[VisionConfig], Any] | None = None,
        idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._camera = camera or shared_camera_preview
        self._config = config or get_vision_config()
        configure_real_runtime = (
            detector_factory is YOLODetector and segmenter_factory is None
        )
        if segmenter_factory is None:
            from app.vision.segmentation import YOLOSegmentation

            segmenter_factory = YOLOSegmentation
        self._detector_factory = detector_factory
        self._segmenter_factory = segmenter_factory
        self._configure_real_runtime = configure_real_runtime
        self._idle_timeout = idle_timeout_seconds
        target_fps = min(
            MAX_INFERENCE_FPS,
            self._config.ai_display_target_fps,
        )
        self._frame_period = 1 / max(target_fps, 0.1)
        self._condition = Condition()
        self._stop = Event()
        self._thread: Thread | None = None
        self._latest: VisionDisplayFrame | None = None
        self._last_access = 0.0
        self._sequence = 0
        self._status = {
            "detection": "initializing",
            "segmentation": "initializing",
            "error": None,
        }
        self._detection_fps = 0.0
        self._segmentation_fps = 0.0
        self._runtime_device = "initializing"

    def start(self) -> None:
        with self._condition:
            self._last_access = monotonic()
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._status = {
                "detection": "warming",
                "segmentation": "warming",
                "error": None,
            }
            self._latest = None
            self._thread = Thread(
                target=self._run,
                name="cityresponder-vision-display",
                daemon=True,
            )
            self._thread.start()

    def status(self) -> dict[str, Any]:
        with self._condition:
            result: dict[str, Any] = dict(self._status)
            if self._latest is not None:
                age_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - self._latest.timestamp).total_seconds(),
                )
                result["last_frame_age_ms"] = age_seconds * 1000
                if age_seconds > INFERENCE_FRESH_SECONDS:
                    for key in ("detection", "segmentation"):
                        if result[key] == "active":
                            result[key] = "stale"
            else:
                result["last_frame_age_ms"] = None
            result["inference_device"] = self._runtime_device
            return result

    def latest(
        self,
        *,
        timeout_seconds: float = 0.5,
        after_sequence: int | None = None,
    ) -> VisionDisplayFrame:
        self.start()
        with self._condition:
            self._last_access = monotonic()
            if self._latest is not None and (
                after_sequence is None or self._latest.sequence > after_sequence
            ):
                return self._latest
            previous = self._sequence if after_sequence is None else after_sequence
            self._condition.wait_for(
                lambda: self._sequence > previous or self._status["error"] is not None,
                timeout=timeout_seconds,
            )
            self._last_access = monotonic()
            if self._latest is not None and (
                after_sequence is None or self._latest.sequence > after_sequence
            ):
                return self._latest
            if self._status["error"] is not None:
                raise VisionDisplayUnavailable(str(self._status["error"]))
            raise TimeoutError("AI inference is warming up")

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)

    def _run(self) -> None:
        detector = self._detector_factory(self._config)
        segmenter = self._segmenter_factory(self._config)
        detector_ready = False
        segmenter_ready = False
        previous_frame_id: str | None = None
        last_inference_at = 0.0
        detection_samples = 0
        segmentation_samples = 0
        sample_window_start = monotonic()
        log_window_start = sample_window_start
        log_samples = 0
        runtime_device = self._config.inference_device
        try:
            if self._configure_real_runtime:
                runtime = configure_torch_runtime(
                    self._config.inference_cpu_threads,
                    self._config.inference_device,
                )
                runtime_device = runtime.get("device", "unavailable")
            self._runtime_device = runtime_device
            self._camera.start()
            for name, runner in (("detection", detector), ("segmentation", segmenter)):
                started = perf_counter()
                try:
                    runner._load_model()
                    with self._condition:
                        self._status[name] = "warming"
                        self._condition.notify_all()
                    logger.info(
                        "Observation model loaded: model=%s load_ms=%.1f",
                        name,
                        (perf_counter() - started) * 1000,
                    )
                    if name == "detection":
                        detector_ready = True
                    else:
                        segmenter_ready = True
                except Exception as exc:
                    logger.exception("Observation model load failed: model=%s", name)
                    with self._condition:
                        self._status[name] = "error"
                        self._status["error"] = f"{name.title()} model unavailable ({type(exc).__name__})"
                        self._condition.notify_all()

            while not self._stop.is_set():
                now = monotonic()
                with self._condition:
                    if now - self._last_access > self._idle_timeout:
                        return
                try:
                    reader = getattr(self._camera, "latest_display_raw", self._camera.latest_raw)
                    captured = reader(
                        timeout_seconds=0.5,
                        after_frame_id=previous_frame_id,
                    )
                except TimeoutError:
                    continue
                except CameraPreviewUnavailable as exc:
                    with self._condition:
                        self._status["error"] = "Camera unavailable"
                        self._condition.notify_all()
                    logger.warning("Observation inference waiting for camera: %s", type(exc).__name__)
                    if self._stop.wait(0.2):
                        return
                    continue

                if captured.metadata.frame_id == previous_frame_id:
                    continue
                previous_frame_id = captured.metadata.frame_id
                now = monotonic()
                remaining = self._frame_period - (now - last_inference_at)
                if last_inference_at and remaining > 0:
                    if self._stop.wait(min(remaining, 0.05)):
                        return
                    continue

                raw = captured.frame
                detection_started = perf_counter()
                detections: list[Detection] = []
                detection_latency_ms: float | None = None
                if detector_ready:
                    try:
                        detections = [
                            item.model_copy(
                                update={"coordinate_system": CoordinateSystem.DISPLAY_MODEL_CROP}
                            )
                            for item in detector.detect(raw)
                        ]
                        detection_latency_ms = (perf_counter() - detection_started) * 1000
                        detection_samples += 1
                        with self._condition:
                            self._status["detection"] = "active"
                            self._condition.notify_all()
                    except Exception as exc:
                        logger.warning("Observation detection failed: %s", type(exc).__name__)
                        with self._condition:
                            self._status["detection"] = "error"
                            self._status["error"] = f"Detection inference unavailable ({type(exc).__name__})"
                            self._condition.notify_all()

                segmentation_started = perf_counter()
                segmentations: list[SegmentationDetection] = []
                segmentation_latency_ms: float | None = None
                if segmenter_ready:
                    try:
                        segmentations = [
                            item.model_copy(
                                update={"coordinate_system": CoordinateSystem.DISPLAY_MODEL_CROP}
                            )
                            for item in segmenter.segment(raw)
                        ]
                        segmentation_latency_ms = (perf_counter() - segmentation_started) * 1000
                        segmentation_samples += 1
                        with self._condition:
                            self._status["segmentation"] = "active"
                            self._condition.notify_all()
                    except Exception as exc:
                        logger.warning("Observation segmentation failed: %s", type(exc).__name__)
                        with self._condition:
                            self._status["segmentation"] = "error"
                            self._status["error"] = f"Segmentation inference unavailable ({type(exc).__name__})"
                            self._condition.notify_all()

                finished_at = datetime.now(timezone.utc)
                inference_latency_ms = (perf_counter() - detection_started) * 1000
                camera_fps = self._camera.performance_snapshot()["capture_fps"]
                try:
                    annotated = annotate_frame(raw, detections, segmentations)
                    preview_width, preview_height = _preview_size(annotated.shape[1], annotated.shape[0])
                    if (preview_width, preview_height) != (annotated.shape[1], annotated.shape[0]):
                        annotated = cv2.resize(
                            annotated,
                            (preview_width, preview_height),
                            interpolation=cv2.INTER_AREA,
                        )
                    encoded, buffer = cv2.imencode(
                        ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                    )
                    if not encoded or len(buffer) > MAX_RESULT_BYTES:
                        raise RuntimeError("Annotated JPEG exceeded the configured frame limit")
                except Exception as exc:
                    logger.exception("Observation frame annotation failed")
                    with self._condition:
                        self._status["error"] = f"Annotated frame unavailable ({type(exc).__name__})"
                        self._condition.notify_all()
                    if self._stop.wait(0.2):
                        return
                    continue

                duration = max(monotonic() - sample_window_start, 0.001)
                self._detection_fps = detection_samples / duration
                self._segmentation_fps = segmentation_samples / duration
                last_inference_at = monotonic()
                with self._condition:
                    self._sequence += 1
                    self._latest = VisionDisplayFrame(
                        jpeg=buffer.tobytes(),
                        frame_id=captured.metadata.frame_id,
                        timestamp=captured.metadata.timestamp,
                        processed_at=finished_at,
                        capture_width=raw.shape[1],
                        capture_height=raw.shape[0],
                        preview_width=preview_width,
                        preview_height=preview_height,
                        sequence=self._sequence,
                        detections=tuple(item.model_dump(mode="json") for item in detections),
                        segmentations=tuple(item.model_dump(mode="json") for item in segmentations),
                        detection_status=self._status["detection"] or "error",
                        segmentation_status=self._status["segmentation"] or "error",
                        detection_fps=self._detection_fps,
                        segmentation_fps=self._segmentation_fps,
                        detection_latency_ms=detection_latency_ms,
                        segmentation_latency_ms=segmentation_latency_ms,
                        inference_latency_ms=inference_latency_ms,
                        camera_fps=camera_fps,
                        inference_device=runtime_device,
                        source_width=captured.metadata.source_width,
                        source_height=captured.metadata.source_height,
                        crop_origin_x=captured.metadata.crop_origin_x,
                        crop_origin_y=captured.metadata.crop_origin_y,
                        crop_right_x=captured.metadata.crop_right_x,
                        crop_bottom_y=captured.metadata.crop_bottom_y,
                    )
                    self._status["error"] = None
                    self._condition.notify_all()

                log_samples += 1
                if log_samples >= 20:
                    elapsed = max(monotonic() - log_window_start, 0.001)
                    logger.info(
                        "Observation inference: fps=%.2f detection_ms=%s segmentation_ms=%s frame_age_ms=%.1f jpeg_bytes=%s device=%s",
                        log_samples / elapsed,
                        round(detection_latency_ms, 1) if detection_latency_ms is not None else "error",
                        round(segmentation_latency_ms, 1) if segmentation_latency_ms is not None else "error",
                        max(0.0, (finished_at - captured.metadata.timestamp).total_seconds() * 1000),
                        len(buffer),
                        runtime_device,
                    )
                    log_samples = 0
                    log_window_start = monotonic()
                    sample_window_start = log_window_start
                    detection_samples = 0
                    segmentation_samples = 0
        finally:
            with self._condition:
                self._thread = None
                if self._status["error"] is None:
                    self._status = {
                        "detection": "idle",
                        "segmentation": "idle",
                        "error": None,
                    }
                self._condition.notify_all()


def annotate_frame(
    frame: np.ndarray,
    detections: list[Detection],
    segmentations: list[SegmentationDetection],
) -> np.ndarray:
    """Render real model outputs on their own native source frame."""

    annotated = frame.copy()
    mask_layer = frame.copy()
    for item in segmentations:
        points = np.rint([[point.x, point.y] for point in item.polygon]).astype(np.int32)
        if len(points) < 3:
            continue
        color = CLASS_COLORS.get(item.class_name, (0, 180, 255))
        cv2.fillPoly(mask_layer, [points], color)
    if segmentations:
        cv2.addWeighted(mask_layer, 0.26, annotated, 0.74, 0, dst=annotated)

    for item in segmentations:
        points = np.rint([[point.x, point.y] for point in item.polygon]).astype(np.int32)
        if len(points) < 3:
            continue
        color = CLASS_COLORS.get(item.class_name, (0, 180, 255))
        cv2.polylines(annotated, [points], True, color, 3, cv2.LINE_AA)
        box = item.bounding_box
        _draw_label(
            annotated,
            f"{item.class_name} {item.confidence:.2f}",
            (int(box.x1), int(box.y1)),
            color,
        )

    for item in detections:
        box = item.bounding_box
        color = CLASS_COLORS.get(item.class_name, (255, 255, 0))
        first = (round(box.x1), round(box.y1))
        second = (round(box.x2), round(box.y2))
        cv2.rectangle(annotated, first, second, color, 3, cv2.LINE_AA)
        _draw_label(
            annotated,
            f"{item.class_name} {item.confidence:.2f}",
            first,
            color,
        )
    return annotated


def _draw_label(frame: np.ndarray, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    x = max(0, min(origin[0], frame.shape[1] - 1))
    y = max(24, min(origin[1], frame.shape[0] - 1))
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.55, min(frame.shape[1] / 1400, 0.9))
    (width, height), baseline = cv2.getTextSize(text, font, scale, 2)
    top = max(0, y - height - baseline - 4)
    cv2.rectangle(frame, (x, top), (min(frame.shape[1] - 1, x + width + 8), y), color, -1)
    cv2.putText(frame, text, (x + 4, max(height, y - baseline - 2)), font, scale, (255, 255, 255), 2, cv2.LINE_AA)


def _preview_size(width: int, height: int) -> tuple[int, int]:
    scale = min(PREVIEW_WIDTH / width, PREVIEW_HEIGHT / height, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


shared_vision_display = SharedVisionDisplayService()


def configure_torch_runtime(
    cpu_threads: int, inference_device: str = "auto"
) -> dict[str, Any]:
    """Limit CPU inference thread fan-out so live streaming stays responsive."""

    try:
        import torch
    except Exception:
        logger.exception("Unable to initialize the PyTorch runtime")
        return {"cuda_available": False, "cpu_threads": None, "interop_threads": None}

    try:
        torch.set_num_threads(cpu_threads)
    except Exception:
        logger.exception("Unable to set the PyTorch CPU thread limit")

    try:
        torch.set_num_interop_threads(min(cpu_threads, 2))
    except RuntimeError:
        # PyTorch allows this only before inter-op work starts; later workers
        # reuse the process-wide setting and still apply the intra-op cap.
        pass
    except Exception:
        logger.exception("Unable to set the PyTorch inter-op thread limit")

    try:
        cuda_available = bool(torch.cuda.is_available())
        resolved_device = resolve_inference_device(inference_device)
        if isinstance(resolved_device, int):
            device_name = f"cuda:{resolved_device} ({torch.cuda.get_device_name(resolved_device)})"
        elif str(resolved_device).startswith("cuda:"):
            index = int(str(resolved_device).split(":", 1)[1])
            device_name = f"cuda:{index} ({torch.cuda.get_device_name(index)})"
        else:
            device_name = "cpu"
    except Exception:
        logger.exception("Unable to inspect the PyTorch compute device")
        cuda_available = False
        device_name = "cpu"

    runtime = {
        "cuda_available": cuda_available,
        "device": device_name,
        "cpu_threads": int(torch.get_num_threads()),
        "interop_threads": int(torch.get_num_interop_threads()),
    }
    logger.info(
        "Observation inference runtime: device=%s cpu_threads=%s interop_threads=%s",
        runtime["device"],
        runtime["cpu_threads"],
        runtime["interop_threads"],
    )
    return runtime
