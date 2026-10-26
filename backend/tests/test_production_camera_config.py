from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from fastapi import HTTPException

from app.core.config import Settings
from app.vision.capture import (
    CAMERA_READ_RETRY_ATTEMPTS,
    CaptureOpenError,
    CaptureReadError,
    VisionCaptureService,
)
from app.vision.config import get_vision_config


class ProductionCameraConfigurationTests(unittest.TestCase):
    def test_camera_capture_one_discards_transient_black_warmup_frame(self):
        config = replace(get_vision_config(), source="CAMERA", camera_index=0)
        service = VisionCaptureService(config)

        class SequenceCapture:
            def __init__(self):
                self.frames = [
                    np.zeros((1080, 1920, 3), dtype=np.uint8),
                    np.full((1080, 1920, 3), 120, dtype=np.uint8),
                ]

            def read(self):
                return True, self.frames.pop(0)

        fake_capture = SequenceCapture()
        service._capture = fake_capture
        with patch("app.vision.capture.time.sleep"):
            captured = service.capture_one()

        self.assertIsNotNone(captured)
        assert captured is not None
        self.assertGreater(int(captured.frame.max()), 0)
        self.assertEqual(len(fake_capture.frames), 0)

    def test_camera_capture_one_retries_transient_read_failure(self):
        config = replace(get_vision_config(), source="CAMERA", camera_index=0)
        service = VisionCaptureService(config)

        class SequenceCapture:
            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                if self.reads == 1:
                    return False, None
                return True, np.full((1080, 1920, 3), 120, dtype=np.uint8)

        fake_capture = SequenceCapture()
        service._capture = fake_capture
        with patch("app.vision.capture.time.sleep"):
            captured = service.capture_one()

        self.assertIsNotNone(captured)
        self.assertEqual(fake_capture.reads, 2)

    def test_camera_capture_one_fails_after_bounded_black_frame_retries(self):
        config = replace(get_vision_config(), source="CAMERA", camera_index=0)
        service = VisionCaptureService(config)

        class BlackCapture:
            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                return True, np.zeros((1080, 1920, 3), dtype=np.uint8)

        fake_capture = BlackCapture()
        service._capture = fake_capture
        with patch("app.vision.capture.time.sleep"):
            with self.assertRaisesRegex(CaptureReadError, "non-black frame"):
                service.capture_one()

        self.assertEqual(fake_capture.reads, CAMERA_READ_RETRY_ATTEMPTS)

    def test_requested_camera_environment_names_and_legacy_names_are_supported(self):
        requested = Settings(
            _env_file=None,
            VISION_CAMERA_INDEX="0",
            VISION_CAMERA_BACKEND="DSHOW",
            VISION_CAMERA_FOURCC="MJPG",
            VISION_FRAME_WIDTH="1920",
            VISION_FRAME_HEIGHT="1080",
            VISION_REQUIRE_EXACT_FRAME_SIZE="true",
        )
        self.assertEqual(requested.vision_camera_index, 0)
        self.assertEqual(requested.vision_capture_backend, "DSHOW")
        self.assertEqual(requested.vision_capture_fourcc, "MJPG")
        self.assertEqual((requested.vision_frame_width, requested.vision_frame_height), (1920, 1080))
        self.assertTrue(requested.vision_require_exact_frame_size)

        legacy = Settings(
            _env_file=None,
            vision_camera_index=0,
            VISION_CAPTURE_BACKEND="MSMF",
            VISION_CAPTURE_FOURCC="YUYV",
        )
        self.assertEqual(legacy.vision_capture_backend, "MSMF")
        self.assertEqual(legacy.vision_capture_fourcc, "YUYV")

    def test_camera_source_requires_explicit_device_and_does_not_fallback(self):
        config = replace(
            get_vision_config(),
            source="CAMERA",
            camera_index=None,
        )
        with self.assertRaisesRegex(CaptureOpenError, "VISION_CAMERA_INDEX"):
            VisionCaptureService(config)

    def test_image_file_source_remains_usable_without_camera_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "fixture.png"
            expected = np.full((480, 640, 3), 80, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(image_path), expected))
            config = replace(
                get_vision_config(),
                source=str(image_path),
                camera_index=None,
            )
            service = VisionCaptureService(config)
            try:
                frame = service.read()
            finally:
                service.close()

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.frame.shape, expected.shape)

    def test_video_file_source_remains_usable_without_camera_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            video_path = Path(directory) / "fixture.avi"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"MJPG"),
                10.0,
                (640, 480),
            )
            self.assertTrue(writer.isOpened())
            writer.write(np.full((480, 640, 3), 80, dtype=np.uint8))
            writer.write(np.full((480, 640, 3), 120, dtype=np.uint8))
            writer.release()
            config = replace(
                get_vision_config(),
                source=str(video_path),
                camera_index=None,
            )
            service = VisionCaptureService(config)
            try:
                first = service.read()
                second = service.read()
                end = service.read()
            finally:
                service.close()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNone(end)
        assert first is not None and second is not None
        self.assertEqual(first.frame.shape, (480, 640, 3))
        self.assertEqual(second.frame.shape, (480, 640, 3))

    def test_fastapi_lifespan_does_not_start_live_worker_by_default(self):
        from app import main

        with (
            patch.object(main.settings, "vision_live_enabled", False),
            patch("app.main.initialize_database"),
            patch("app.main.seed_development_users"),
            patch("app.main.set_live_event_loop"),
            patch("app.main.clear_live_event_loop"),
            patch("app.main.mqtt_client.start"),
            patch("app.main.mqtt_client.stop"),
            patch.object(main.shared_vision_frames, "start") as worker_start,
            patch.object(main.shared_vision_frames, "stop"),
        ):
            async def enter_lifespan():
                async with main.lifespan(main.app):
                    pass

            asyncio.run(enter_lifespan())

        worker_start.assert_not_called()

    def test_live_frame_endpoint_explains_disabled_state_without_starting_worker(self):
        from app import main

        with (
            patch.object(main.settings, "vision_preview_enabled", False),
            patch.object(main.settings, "vision_live_enabled", False),
            patch.object(main.shared_vision_frames, "latest") as latest,
        ):
            with self.assertRaises(HTTPException) as raised:
                main.live_annotated_vision_frame(_current_user=None)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("VISION_LIVE_ENABLED=true", raised.exception.detail)
        latest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
