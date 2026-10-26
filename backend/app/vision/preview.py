"""On-demand camera-only preview; no inference, evidence, or publishing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from threading import Condition, Event, Thread
from time import monotonic
from typing import Any, Callable

import cv2

from app.vision.capture import CapturedFrame, VisionCaptureService
from app.vision.config import get_vision_config
from app.vision.schemas import CoordinateSystem, FrameMetadata, FrameSourceType


logger = logging.getLogger(__name__)
TARGET_FPS = 8.0
IDLE_TIMEOUT_SECONDS = 20.0
FRESH_SECONDS = 2.0
MAX_JPEG_BYTES = 1_000_000
READ_INTERVAL_SECONDS = 0.05
REOPEN_AFTER_FAILURES = 3
PREVIEW_WIDTH = 854
PREVIEW_HEIGHT = 480
JPEG_QUALITY = 55


@dataclass(frozen=True)
class CameraPreviewFrame:
    jpeg: bytes
    frame_id: str
    timestamp: datetime
    capture_width: int
    capture_height: int
    preview_width: int
    preview_height: int
    sequence: int
    source_width: int | None = None
    source_height: int | None = None
    crop_origin_x: int = 0
    crop_origin_y: int = 0
    crop_right_x: int | None = None
    crop_bottom_y: int | None = None
    raw_frame: Any | None = None
    camera_fps: float = 0.0
    capture_latency_ms: float = 0.0
    resize_latency_ms: float = 0.0
    jpeg_encode_ms: float = 0.0


class CameraPreviewUnavailable(RuntimeError):
    """No current, valid physical camera frame is available."""


class SharedCameraPreviewService:
    """Own one camera while authenticated viewers poll for raw JPEG frames."""

    def __init__(
        self,
        capture_factory: Callable[[], VisionCaptureService] | None = None,
        *,
        target_fps: float = TARGET_FPS,
        idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS,
        crop_bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        config = get_vision_config() if capture_factory is None else None
        self._capture_factory = capture_factory or (lambda: VisionCaptureService(config))
        self._crop_bounds = crop_bounds or (
            (
                config.display_crop_left,
                config.display_crop_top,
                config.display_crop_right,
                config.display_crop_bottom,
            )
            if capture_factory is None and config is not None
            else (0.0, 0.0, 1.0, 1.0)
        )
        self._frame_period = 1.0 / target_fps
        self._idle_timeout = idle_timeout_seconds
        self._condition = Condition()
        self._stop = Event()
        self._thread: Thread | None = None
        self._latest: CameraPreviewFrame | None = None
        self._latest_raw: CapturedFrame | None = None
        self._latest_display_raw: CapturedFrame | None = None
        self._last_access = 0.0
        self._sequence = 0
        self._raw_sequence = 0
        self._capture_fps = 0.0
        self._state = "idle"

    def start(self) -> None:
        with self._condition:
            self._last_access = monotonic()
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._state = "initializing"
            self._thread = Thread(target=self._run, name="cityresponder-camera-preview", daemon=True)
            self._thread.start()

    def status(self) -> str:
        with self._condition:
            return self._state

    def performance_snapshot(self) -> dict[str, float]:
        """Return non-sensitive live capture and encoding measurements."""

        with self._condition:
            frame = self._latest
            return {
                "capture_fps": self._capture_fps,
                "display_fps": 1.0 / self._frame_period,
                "capture_latency_ms": frame.capture_latency_ms if frame else 0.0,
                "resize_latency_ms": frame.resize_latency_ms if frame else 0.0,
                "jpeg_encode_ms": frame.jpeg_encode_ms if frame else 0.0,
                "jpeg_bytes": float(len(frame.jpeg)) if frame else 0.0,
            }

    def latest(
        self,
        *,
        timeout_seconds: float = 0.5,
        after_sequence: int | None = None,
    ) -> CameraPreviewFrame:
        self.start()
        with self._condition:
            self._last_access = monotonic()
            if (
                self._latest is not None
                and self._fresh(self._latest)
                and (after_sequence is None or self._latest.sequence > after_sequence)
            ):
                return self._latest
            previous_sequence = self._sequence if after_sequence is None else after_sequence
            self._condition.wait_for(
                lambda: self._sequence != previous_sequence or self._state == "error",
                timeout=timeout_seconds,
            )
            self._last_access = monotonic()
            if (
                self._latest is not None
                and self._fresh(self._latest)
                and (after_sequence is None or self._latest.sequence > after_sequence)
            ):
                return self._latest
            if self._state == "error":
                raise CameraPreviewUnavailable("Camera unavailable or no valid frame")
            raise TimeoutError("Camera initializing")

    def latest_raw(
        self,
        *,
        timeout_seconds: float = 0.5,
        after_frame_id: str | None = None,
    ) -> CapturedFrame:
        """Return the latest native frame from this owner's camera read loop."""

        self.start()
        with self._condition:
            self._last_access = monotonic()
            if (
                self._latest_raw is not None
                and self._raw_fresh(self._latest_raw)
                and (after_frame_id is None or self._latest_raw.metadata.frame_id != after_frame_id)
            ):
                return self._latest_raw
            previous_sequence = self._raw_sequence
            self._condition.wait_for(
                lambda: self._raw_sequence != previous_sequence or self._state == "error",
                timeout=timeout_seconds,
            )
            self._last_access = monotonic()
            if (
                self._latest_raw is not None
                and self._raw_fresh(self._latest_raw)
                and (after_frame_id is None or self._latest_raw.metadata.frame_id != after_frame_id)
            ):
                return self._latest_raw
            if self._state == "error":
                raise CameraPreviewUnavailable("Camera unavailable or no valid frame")
            raise TimeoutError("Camera initializing")

    def latest_display_raw(
        self,
        *,
        timeout_seconds: float = 0.5,
        after_frame_id: str | None = None,
    ) -> CapturedFrame:
        """Return the display-only crop while preserving native capture ownership."""

        self.start()
        with self._condition:
            self._last_access = monotonic()
            if (
                self._latest_display_raw is not None
                and self._raw_fresh(self._latest_display_raw)
                and (
                    after_frame_id is None
                    or self._latest_display_raw.metadata.frame_id != after_frame_id
                )
            ):
                return self._latest_display_raw
            previous_sequence = self._raw_sequence
            self._condition.wait_for(
                lambda: self._raw_sequence != previous_sequence or self._state == "error",
                timeout=timeout_seconds,
            )
            self._last_access = monotonic()
            if (
                self._latest_display_raw is not None
                and self._raw_fresh(self._latest_display_raw)
                and (
                    after_frame_id is None
                    or self._latest_display_raw.metadata.frame_id != after_frame_id
                )
            ):
                return self._latest_display_raw
            if self._state == "error":
                raise CameraPreviewUnavailable("Camera unavailable or no valid frame")
            raise TimeoutError("Camera initializing")

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=10.0)

    @staticmethod
    def _fresh(frame: CameraPreviewFrame) -> bool:
        return (datetime.now(frame.timestamp.tzinfo) - frame.timestamp).total_seconds() <= FRESH_SECONDS

    @staticmethod
    def _raw_fresh(frame: CapturedFrame) -> bool:
        return (
            datetime.now(frame.metadata.timestamp.tzinfo) - frame.metadata.timestamp
        ).total_seconds() <= FRESH_SECONDS

    def _run(self) -> None:
        capture: VisionCaptureService | None = None
        measured_since = monotonic()
        capture_measured_since = measured_since
        measured_frames = 0
        captured_frames = 0
        next_encode_at = 0.0
        consecutive_failures = 0
        try:
            while not self._stop.is_set():
                started = monotonic()
                with self._condition:
                    if started - self._last_access > self._idle_timeout:
                        return
                try:
                    if capture is None:
                        capture = self._capture_factory()
                        if capture.source_type is not FrameSourceType.CAMERA:
                            raise CameraPreviewUnavailable("Camera preview requires a physical camera")
                    capture_started = monotonic()
                    captured = capture.capture_one()
                    capture_latency_ms = (monotonic() - capture_started) * 1000
                    if captured is None:
                        raise CameraPreviewUnavailable("Camera did not provide a frame")
                    raw = captured.frame
                    source_height, source_width = raw.shape[:2]
                    if raw.ndim != 3 or raw.shape[2] != 3 or raw.dtype.name != "uint8":
                        raise CameraPreviewUnavailable("Camera frame format is invalid")
                    sample = cv2.cvtColor(raw[::16, ::16], cv2.COLOR_BGR2GRAY)
                    if float(sample.mean()) < 3.0 and float(sample.var()) < 3.0:
                        raise CameraPreviewUnavailable("Camera frame is black")
                    consecutive_failures = 0
                    captured_frames += 1
                    if captured_frames >= 30:
                        capture_now = monotonic()
                        self._capture_fps = captured_frames / max(
                            capture_now - capture_measured_since, 0.001
                        )
                        captured_frames = 0
                        capture_measured_since = capture_now
                    with self._condition:
                        self._latest_raw = captured
                        display_raw, crop = crop_display_frame(raw, self._crop_bounds)
                        display_metadata = FrameMetadata(
                            frame_id=captured.metadata.frame_id,
                            timestamp=captured.metadata.timestamp,
                            source=getattr(captured.metadata, "source", FrameSourceType.CAMERA),
                            width=display_raw.shape[1],
                            height=display_raw.shape[0],
                            coordinate_system=CoordinateSystem.DISPLAY_MODEL_CROP,
                            parent_frame_id=captured.metadata.frame_id,
                            crop_origin_x=crop[0],
                            crop_origin_y=crop[1],
                            source_width=source_width,
                            source_height=source_height,
                            crop_right_x=crop[2],
                            crop_bottom_y=crop[3],
                        )
                        self._latest_display_raw = CapturedFrame(
                            frame=display_raw,
                            metadata=display_metadata,
                        )
                        self._raw_sequence += 1
                        self._condition.notify_all()
                    if monotonic() < next_encode_at:
                        remaining = READ_INTERVAL_SECONDS - (monotonic() - started)
                        if remaining > 0 and self._stop.wait(remaining):
                            return
                        continue
                    resize_started = monotonic()
                    height, width = display_raw.shape[:2]
                    scale = min(PREVIEW_WIDTH / width, PREVIEW_HEIGHT / height, 1.0)
                    preview_width = max(1, round(width * scale))
                    preview_height = max(1, round(height * scale))
                    display = cv2.resize(
                        display_raw,
                        (preview_width, preview_height),
                        interpolation=cv2.INTER_AREA,
                    )
                    resize_latency_ms = (monotonic() - resize_started) * 1000
                    encode_started = monotonic()
                    encoded, buffer = cv2.imencode(
                        ".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                    )
                    jpeg_encode_ms = (monotonic() - encode_started) * 1000
                    if not encoded or len(buffer) > MAX_JPEG_BYTES:
                        raise CameraPreviewUnavailable("Camera JPEG could not be encoded within the preview limit")
                    with self._condition:
                        self._sequence += 1
                        self._latest = CameraPreviewFrame(
                            jpeg=buffer.tobytes(),
                            frame_id=captured.metadata.frame_id,
                            timestamp=captured.metadata.timestamp,
                            capture_width=width,
                            capture_height=height,
                            preview_width=preview_width,
                            preview_height=preview_height,
                            sequence=self._sequence,
                            source_width=source_width,
                            source_height=source_height,
                            crop_origin_x=crop[0],
                            crop_origin_y=crop[1],
                            crop_right_x=crop[2],
                            crop_bottom_y=crop[3],
                            raw_frame=display_raw,
                            camera_fps=self._capture_fps,
                            capture_latency_ms=capture_latency_ms,
                            resize_latency_ms=resize_latency_ms,
                            jpeg_encode_ms=jpeg_encode_ms,
                        )
                        self._state = "ready"
                        self._condition.notify_all()
                    next_encode_at = monotonic() + self._frame_period
                    measured_frames += 1
                    if measured_frames >= 30:
                        elapsed = monotonic() - measured_since
                        logger.info(
                            "Camera-only preview: fps=%.2f source=%sx%s crop=%s,%s-%s,%s display=%sx%s jpeg_bytes=%s",
                            measured_frames / elapsed,
                            source_width,
                            source_height,
                            crop[0],
                            crop[1],
                            crop[2],
                            crop[3],
                            width,
                            height,
                            len(buffer),
                        )
                        measured_since = monotonic()
                        measured_frames = 0
                except Exception as exc:
                    consecutive_failures += 1
                    logger.warning(
                        "Camera-only preview frame failed: %s (consecutive=%s)",
                        type(exc).__name__,
                        consecutive_failures,
                    )
                    with self._condition:
                        self._state = "error"
                        self._condition.notify_all()
                    if capture is not None and consecutive_failures >= REOPEN_AFTER_FAILURES:
                        capture.close()
                        capture = None
                        consecutive_failures = 0
                        next_encode_at = 0.0
                    if self._stop.wait(0.2):
                        return
                    with self._condition:
                        self._state = "initializing"
                        self._condition.notify_all()
                    continue
                remaining = READ_INTERVAL_SECONDS - (monotonic() - started)
                if remaining > 0 and self._stop.wait(remaining):
                    return
        finally:
            if capture is not None:
                capture.close()
            with self._condition:
                self._thread = None
                self._state = "idle"
                self._condition.notify_all()


shared_camera_preview = SharedCameraPreviewService()


def crop_display_frame(
    frame: Any,
    bounds: tuple[float, float, float, float],
) -> tuple[Any, tuple[int, int, int, int]]:
    """Crop a BGR frame using normalized display-only bounds."""

    if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
        raise CameraPreviewUnavailable("Display crop requires a valid image frame")
    height, width = frame.shape[:2]
    left, top, right, bottom = bounds
    if not (
        0.0 <= left < right <= 1.0
        and 0.0 <= top < bottom <= 1.0
    ):
        raise CameraPreviewUnavailable("Display crop bounds are invalid")
    x1 = max(0, min(width - 1, round(width * left)))
    y1 = max(0, min(height - 1, round(height * top)))
    x2 = max(x1 + 1, min(width, round(width * right)))
    y2 = max(y1 + 1, min(height, round(height * bottom)))
    return frame[y1:y2, x1:x2], (x1, y1, x2, y2)
