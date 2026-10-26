"""Camera-only preview contract using synthetic frames, never production capture."""

from datetime import datetime, timezone
from types import SimpleNamespace
from time import sleep
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.vision.preview import CameraPreviewFrame, SharedCameraPreviewService, crop_display_frame
from app.vision.schemas import CoordinateSystem, FrameSourceType


class FakeCapture:
    source_type = FrameSourceType.CAMERA

    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    def capture_one(self):
        self.reads += 1
        frame = np.full((1080, 1920, 3), 90 + self.reads, dtype=np.uint8)
        return SimpleNamespace(
            frame=frame,
            metadata=SimpleNamespace(
                frame_id=f"synthetic-{self.reads}",
                timestamp=datetime.now(timezone.utc),
            ),
        )

    def close(self) -> None:
        self.closed = True


def test_one_shared_camera_owner_and_native_capture_coordinates():
    captures: list[FakeCapture] = []

    def factory():
        capture = FakeCapture()
        captures.append(capture)
        return capture

    service = SharedCameraPreviewService(factory, target_fps=8, idle_timeout_seconds=2)
    try:
        service.start()
        service.start()
        frame = service.latest(timeout_seconds=3)
        assert len(captures) == 1
        assert frame.capture_width == 1920
        assert frame.capture_height == 1080
        assert (frame.preview_width, frame.preview_height) == (853, 480)
        assert frame.jpeg.startswith(b"\xff\xd8")
        assert len(frame.jpeg) < 1_000_000
        assert frame.frame_id.startswith("synthetic-")
    finally:
        service.stop()
    assert captures[0].closed


def test_normalized_model_crop_has_exact_native_bounds_without_scaling():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[:, :, 0] = np.arange(1920, dtype=np.uint16) % 256
    cropped, bounds = crop_display_frame(frame, (0.06, 0.0, 0.82, 1.0))
    assert bounds == (115, 0, 1574, 1080)
    assert cropped.shape == (1080, 1459, 3)
    assert np.array_equal(cropped[:, 0], frame[:, 115])
    assert np.array_equal(cropped[:, -1], frame[:, 1573])


def test_preview_and_inference_share_the_same_model_crop_metadata():
    capture = FakeCapture()
    service = SharedCameraPreviewService(
        lambda: capture,
        target_fps=8,
        idle_timeout_seconds=2,
        crop_bounds=(0.06, 0.0, 0.82, 1.0),
    )
    try:
        preview = service.latest(timeout_seconds=3)
        display = service.latest_display_raw(timeout_seconds=3)
        native = service.latest_raw(timeout_seconds=3)
        assert (preview.capture_width, preview.capture_height) == (1459, 1080)
        assert (preview.preview_width, preview.preview_height) == (648, 480)
        assert (preview.source_width, preview.source_height) == (1920, 1080)
        assert (preview.crop_origin_x, preview.crop_right_x) == (115, 1574)
        assert display.frame.shape == (1080, 1459, 3)
        assert display.metadata.coordinate_system is CoordinateSystem.DISPLAY_MODEL_CROP
        assert display.metadata.source_width == 1920
        assert native.frame.shape == (1080, 1920, 3)
    finally:
        service.stop()


def test_camera_owner_releases_after_viewers_stop_polling():
    captures: list[FakeCapture] = []

    def factory():
        capture = FakeCapture()
        captures.append(capture)
        return capture

    service = SharedCameraPreviewService(factory, target_fps=10, idle_timeout_seconds=0.3)
    try:
        service.latest(timeout_seconds=3)
        sleep(0.8)
        assert captures[0].closed
        assert service.status() == "idle"
    finally:
        service.stop()


def test_temporary_black_frame_recovers_without_fabricating_an_image():
    captures: list[FakeCapture] = []

    class BlackCapture(FakeCapture):
        def capture_one(self):
            captured = super().capture_one()
            captured.frame.fill(0)
            return captured

    def factory():
        capture = BlackCapture() if not captures else FakeCapture()
        captures.append(capture)
        return capture

    service = SharedCameraPreviewService(factory, target_fps=8, idle_timeout_seconds=4)
    try:
        frame = None
        for _ in range(12):
            try:
                frame = service.latest(timeout_seconds=0.5)
                break
            except (TimeoutError, RuntimeError):
                sleep(0.2)
        assert frame is not None
        assert len(captures) == 2
        assert captures[0].closed
        assert frame.frame_id.startswith("synthetic-")
    finally:
        service.stop()


def test_preview_and_inference_flags_cannot_be_enabled_together():
    with pytest.raises(ValueError, match="Camera-only preview"):
        Settings(_env_file=None, vision_preview_enabled=True, vision_live_enabled=True)
    with pytest.raises(ValueError, match="Camera-only preview"):
        Settings(_env_file=None, vision_preview_enabled=True, vision_publish_evidence_enabled=True)


def test_display_crop_bounds_are_normalized_and_ordered():
    with pytest.raises(ValueError, match="normalized"):
        Settings(_env_file=None, vision_display_crop_left=-0.01)
    with pytest.raises(ValueError, match="before"):
        Settings(
            _env_file=None,
            vision_display_crop_left=0.82,
            vision_display_crop_right=0.06,
        )


def test_preview_endpoint_has_camera_only_headers_and_conditional_response():
    from app import main

    frame = CameraPreviewFrame(
        jpeg=b"\xff\xd8synthetic",
        frame_id="synthetic-frame",
        timestamp=datetime.now(timezone.utc),
        capture_width=1920,
        capture_height=1080,
        preview_width=1280,
        preview_height=720,
        sequence=1,
    )
    with (
        patch.object(main.settings, "vision_preview_enabled", True),
        patch.object(main.shared_camera_preview, "latest", return_value=frame) as latest,
        patch.object(main.shared_vision_frames, "latest") as inference,
    ):
        response = main.live_annotated_vision_frame(if_none_match=None, _current_user=None)
        assert response.status_code == 200
        assert response.body == frame.jpeg
        assert response.headers["X-CityResponder-Frame-Mode"] == "camera-only"
        assert response.headers["X-CityResponder-Capture-Width"] == "1920"
        assert response.headers["X-CityResponder-Capture-Height"] == "1080"
        assert response.headers["Cache-Control"] == "no-store"
        conditional = main.live_annotated_vision_frame(
            if_none_match=response.headers["ETag"], _current_user=None
        )
        assert conditional.status_code == 304
        assert not conditional.body
        assert latest.call_count == 2
        inference.assert_not_called()


def test_preview_endpoint_stays_disabled_without_explicit_flag():
    from app import main

    with (
        patch.object(main.settings, "vision_preview_enabled", False),
        patch.object(main.settings, "vision_live_enabled", False),
        patch.object(main.shared_camera_preview, "latest") as preview,
    ):
        with pytest.raises(HTTPException) as exc:
            main.live_annotated_vision_frame(if_none_match=None, _current_user=None)
        assert exc.value.status_code == 503
        preview.assert_not_called()
