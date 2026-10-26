"""OpenCV capture service independent from future vision inference."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import CoordinateSystem, FrameMetadata, FrameSourceType


logger = logging.getLogger(__name__)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
CAMERA_READ_RETRY_ATTEMPTS = 5
CAMERA_READ_RETRY_DELAY_SECONDS = 0.1


class VisionCaptureError(RuntimeError):
    """Base error for capture setup and frame-read failures."""


class CaptureOpenError(VisionCaptureError):
    """Raised when a configured camera or file cannot be opened."""


class CaptureReadError(VisionCaptureError):
    """Raised when an open camera cannot provide a frame."""


class TransientCameraReadError(CaptureReadError):
    """Raised for a camera read that may succeed on a short retry."""


@dataclass(frozen=True)
class CapturedFrame:
    """Raw in-memory frame paired with reusable metadata."""

    frame: Any
    metadata: FrameMetadata


class VisionCaptureService:
    """Capture shared frames from a camera, video file, or image file."""

    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or get_vision_config()
        self._capture: cv2.VideoCapture | None = None
        self._image: Any | None = None
        self._finished = False
        self.source_type, self._source_value = self._resolve_source(self.config.source)

    def open(self) -> None:
        """Open the configured source, raising a clear error on failure."""

        if self._finished or self._capture is not None or self._image is not None:
            return

        if self.source_type is FrameSourceType.IMAGE_FILE:
            image = cv2.imread(str(self._source_value), cv2.IMREAD_COLOR)
            if image is None:
                message = f"Unable to open image file: {self._source_value}"
                logger.error(message)
                raise CaptureOpenError(message)
            self._image = image
            return

        if self.source_type is FrameSourceType.CAMERA:
            backend_code = _capture_backend_code(self.config.capture_backend)
            fourcc = None
            if self.config.capture_fourcc:
                fourcc = self.config.capture_fourcc.strip().upper()
                if len(fourcc) != 4 or not fourcc.isascii():
                    raise CaptureOpenError(
                        "Configured camera FOURCC must contain exactly four ASCII characters"
                    )
            if backend_code is None:
                capture = cv2.VideoCapture(self._source_value)
            else:
                capture = cv2.VideoCapture(self._source_value, backend_code)
            try:
                if fourcc:
                    fourcc_set = capture.set(
                        cv2.CAP_PROP_FOURCC,
                        cv2.VideoWriter_fourcc(*fourcc),
                    )
                    if not fourcc_set:
                        logger.warning(
                            "Camera index %s rejected requested FOURCC %s",
                            self._source_value,
                            fourcc,
                        )
                width_set = capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
                height_set = capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
            except Exception:
                capture.release()
                raise
        else:
            capture = cv2.VideoCapture(self._source_value)
            width_set = height_set = None
        if not capture.isOpened():
            capture.release()
            message = f"Unable to open {self.source_type.value} source: {self._source_value}"
            logger.error(message)
            raise CaptureOpenError(message)
        self._capture = capture
        if self.source_type is FrameSourceType.CAMERA:
            try:
                actual_backend = capture.getBackendName()
            except (AttributeError, cv2.error):
                actual_backend = "unknown"
            actual_width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            actual_height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            actual_fourcc = _decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
            actual_fps = capture.get(cv2.CAP_PROP_FPS)
            logger.info(
                "Camera opened: configured_index=%s backend_requested=%s "
                "backend_actual=%s fourcc_requested=%s fourcc_actual=%s "
                "resolution_requested=%sx%s resolution_reported=%sx%s "
                "fps_reported=%.3f width_set=%s height_set=%s",
                self._source_value,
                self.config.capture_backend or "CAP_ANY",
                actual_backend,
                self.config.capture_fourcc or "driver default",
                actual_fourcc or "unknown",
                self.config.frame_width,
                self.config.frame_height,
                actual_width,
                actual_height,
                actual_fps,
                width_set,
                height_set,
            )

    def read(self) -> CapturedFrame | None:
        """Read the next frame, returning None at a clean file/image end."""

        if self._finished:
            return None
        self.open()

        if self.source_type is FrameSourceType.IMAGE_FILE:
            frame = self._image
            self._image = None
            self._finished = True
        else:
            assert self._capture is not None
            success, frame = self._capture.read()
            if not success or frame is None:
                if self.source_type is FrameSourceType.VIDEO_FILE:
                    self.close()
                    self._finished = True
                    return None
                message = "Camera opened but did not provide a frame"
                logger.error(message)
                raise TransientCameraReadError(message)

        height, width = frame.shape[:2]
        if self.source_type is FrameSourceType.CAMERA:
            logger.debug(
                "Camera read: configured_index=%s read_success=true "
                "frame_resolution=%sx%s dtype=%s",
                self._source_value,
                width,
                height,
                getattr(frame, "dtype", "unknown"),
            )
        if (
            self.source_type is FrameSourceType.CAMERA
            and self.config.require_exact_frame_size
            and (width != self.config.frame_width or height != self.config.frame_height)
        ):
            message = (
                f"Camera returned {width}x{height}; locked configuration requires "
                f"{self.config.frame_width}x{self.config.frame_height}"
            )
            logger.error(message)
            raise CaptureReadError(message)
        if (
            width < self.config.building_roi_min_width_px
            or height < self.config.building_roi_min_height_px
        ):
            message = (
                f"Captured frame is {width}x{height}; minimum supported frame is "
                f"{self.config.building_roi_min_width_px}x"
                f"{self.config.building_roi_min_height_px}"
            )
            logger.error(message)
            raise CaptureReadError(message)

        metadata = FrameMetadata(
            frame_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=self.source_type,
            width=width,
            height=height,
            coordinate_system=CoordinateSystem.RAW_CAMERA,
        )
        return CapturedFrame(frame=frame, metadata=metadata)

    def capture_one(self) -> CapturedFrame | None:
        """Read a frame, retrying brief camera warm-up and transport failures."""

        if self.source_type is not FrameSourceType.CAMERA:
            return self.read()

        last_error = "Camera returned an all-black frame"
        for attempt in range(CAMERA_READ_RETRY_ATTEMPTS):
            try:
                captured = self.read()
            except TransientCameraReadError as exc:
                last_error = str(exc)
                logger.warning(
                    "Transient camera read failure on attempt %s/%s: %s",
                    attempt + 1,
                    CAMERA_READ_RETRY_ATTEMPTS,
                    last_error,
                )
            else:
                if captured is None:
                    return None
                if captured.frame.any():
                    return captured
                last_error = "Camera returned an all-black frame"
                logger.warning(
                    "Discarding all-black camera warm-up frame on attempt %s/%s",
                    attempt + 1,
                    CAMERA_READ_RETRY_ATTEMPTS,
                )

            if attempt + 1 < CAMERA_READ_RETRY_ATTEMPTS:
                time.sleep(CAMERA_READ_RETRY_DELAY_SECONDS)

        raise CaptureReadError(
            "Camera did not provide a non-black frame after "
            f"{CAMERA_READ_RETRY_ATTEMPTS} attempts: {last_error}"
        )

    def close(self) -> None:
        """Release an open camera/video resource."""

        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._image = None

    def __enter__(self) -> "VisionCaptureService":
        self.open()
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()

    def _resolve_source(self, source: str) -> tuple[FrameSourceType, int | str]:
        normalized = source.strip()
        if normalized.upper() == "CAMERA" or normalized.isdigit():
            camera_index = self.config.camera_index
            if camera_index is None and normalized.isdigit():
                camera_index = int(normalized)
            if camera_index is None:
                raise CaptureOpenError(
                    "VISION_CAMERA_INDEX must be configured before opening a camera"
                )
            return FrameSourceType.CAMERA, camera_index
        if Path(normalized).suffix.lower() in IMAGE_SUFFIXES:
            return FrameSourceType.IMAGE_FILE, normalized
        return FrameSourceType.VIDEO_FILE, normalized


def _capture_backend_code(name: str | None) -> int | None:
    if name is None or not name.strip() or name.strip().upper() in {"ANY", "CAP_ANY"}:
        return None
    normalized = name.strip().upper().removeprefix("CAP_")
    supported = {
        "DSHOW": "CAP_DSHOW",
        "MSMF": "CAP_MSMF",
        "V4L2": "CAP_V4L2",
        "AVFOUNDATION": "CAP_AVFOUNDATION",
    }
    attribute = supported.get(normalized)
    if attribute is None or not hasattr(cv2, attribute):
        raise CaptureOpenError(f"Unsupported or unavailable camera backend: {name}")
    return int(getattr(cv2, attribute))


def _decode_fourcc(value: float) -> str:
    packed = int(round(value))
    decoded = "".join(chr((packed >> (8 * index)) & 0xFF) for index in range(4))
    return decoded.rstrip("\x00 ")
