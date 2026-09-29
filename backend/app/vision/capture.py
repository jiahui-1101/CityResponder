"""OpenCV capture service independent from future vision inference."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any

import cv2

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import FrameMetadata, FrameSourceType


logger = logging.getLogger(__name__)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class VisionCaptureError(RuntimeError):
    """Base error for capture setup and frame-read failures."""


class CaptureOpenError(VisionCaptureError):
    """Raised when a configured camera or file cannot be opened."""


class CaptureReadError(VisionCaptureError):
    """Raised when an open camera cannot provide a frame."""


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
        self._frame_ids = count(1)
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

        capture = cv2.VideoCapture(self._source_value)
        if self.source_type is FrameSourceType.CAMERA:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        if not capture.isOpened():
            capture.release()
            message = f"Unable to open {self.source_type.value} source: {self._source_value}"
            logger.error(message)
            raise CaptureOpenError(message)
        self._capture = capture

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
                raise CaptureReadError(message)

        height, width = frame.shape[:2]
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
            frame_id=str(next(self._frame_ids)),
            timestamp=datetime.now(timezone.utc),
            source=self.source_type,
            width=width,
            height=height,
        )
        return CapturedFrame(frame=frame, metadata=metadata)

    def capture_one(self) -> CapturedFrame | None:
        """Read one frame through the same API used by both future branches."""

        return self.read()

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
            return FrameSourceType.CAMERA, self.config.camera_index
        if Path(normalized).suffix.lower() in IMAGE_SUFFIXES:
            return FrameSourceType.IMAGE_FILE, normalized
        return FrameSourceType.VIDEO_FILE, normalized
