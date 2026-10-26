"""Deterministic tests for observation-only camera inference display."""

from datetime import datetime, timezone
from datetime import timedelta
from threading import Lock
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.vision.config import get_vision_config
from app.vision.device import resolve_inference_device
from app.vision.inference_display import (
    AIFramePresentationPolicy,
    SharedVisionDisplayService,
    annotate_frame,
    configure_torch_runtime,
)
from app.vision.detector import DetectorInferenceError, YOLODetector
from app.vision.segmentation import SegmentationInferenceError, YOLOSegmentation
from app.auth.models import UserRole
from app.vision.capture import CapturedFrame
from app.vision.schemas import (
    BoundingBox,
    Detection,
    FrameMetadata,
    FrameSourceType,
    CoordinateSystem,
    PolygonPoint,
    SegmentationDetection,
)


class SyntheticSharedCamera:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sequence = 0
        self._last_access = 0.0
        self._next_frame_at = 0.0

    def start(self):
        return None

    def latest_raw(self, *, timeout_seconds=0.5, after_frame_id=None):
        deadline = __import__("time").monotonic() + timeout_seconds
        while __import__("time").monotonic() <= deadline:
            with self._lock:
                now = __import__("time").monotonic()
                self._last_access = now
                if after_frame_id != f"synthetic-{self._sequence}" or now >= self._next_frame_at:
                    self._sequence += 1
                    self._next_frame_at = now + 0.05
                    frame_id = f"synthetic-{self._sequence}"
                    frame = np.full((1080, 1920, 3), 72, dtype=np.uint8)
                    metadata = FrameMetadata(
                        frame_id=frame_id,
                        timestamp=datetime.now(timezone.utc),
                        source=FrameSourceType.CAMERA,
                        width=1920,
                        height=1080,
                    )
                    return CapturedFrame(frame=frame, metadata=metadata)
            sleep(0.01)
        raise TimeoutError("synthetic camera timeout")

    def performance_snapshot(self):
        return {"capture_fps": 20.0}


class SyntheticDetector:
    def __init__(self, _config) -> None:
        self.last_inference_duration_ms = 5.0

    def _load_model(self):
        return object()

    def detect(self, _frame):
        return [
            Detection(
                class_name="PERSON",
                confidence=0.91,
                bounding_box=BoundingBox(x1=100, y1=120, x2=200, y2=300),
            )
        ]


class SyntheticSegmenter:
    def __init__(self, _config) -> None:
        self.last_inference_duration_ms = 6.0

    def _load_model(self):
        return object()

    def segment(self, _frame):
        return [
            SegmentationDetection(
                class_name="POTHOLE",
                confidence=0.88,
                bounding_box=BoundingBox(x1=300, y1=300, x2=500, y2=500),
                polygon=[
                    PolygonPoint(x=300, y=300),
                    PolygonPoint(x=500, y=300),
                    PolygonPoint(x=450, y=500),
                    PolygonPoint(x=300, y=480),
                ],
            )
        ]


def test_ai_display_uses_shared_native_frame_and_keeps_results_synchronized():
    camera = SyntheticSharedCamera()
    service = SharedVisionDisplayService(
        camera,
        config=get_vision_config(),
        detector_factory=SyntheticDetector,
        segmenter_factory=SyntheticSegmenter,
        idle_timeout_seconds=2,
    )
    try:
        frame = service.latest(timeout_seconds=5)
        decoded = cv2.imdecode(np.frombuffer(frame.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert frame.frame_id.startswith("synthetic-")
        assert (frame.capture_width, frame.capture_height) == (1920, 1080)
        assert (frame.preview_width, frame.preview_height) == (853, 480)
        assert decoded is not None and decoded.shape[:2] == (480, 853)
        assert frame.detection_status == "active"
        assert frame.segmentation_status == "active"
        assert frame.detections[0]["class_name"] == "PERSON"
        assert frame.segmentations[0]["class_name"] == "POTHOLE"
        assert frame.detections[0]["coordinate_system"] == CoordinateSystem.DISPLAY_MODEL_CROP.value
        assert frame.segmentations[0]["coordinate_system"] == CoordinateSystem.DISPLAY_MODEL_CROP.value
        assert frame.inference_latency_ms > 0
        assert len(frame.jpeg) < 1_000_000
    finally:
        service.stop()


def test_annotation_uses_native_polygon_and_box_coordinates():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    box = Detection(
        class_name="PERSON",
        confidence=0.9,
        bounding_box=BoundingBox(x1=10, y1=10, x2=30, y2=30),
    )
    mask = SegmentationDetection(
        class_name="POTHOLE",
        confidence=0.8,
        bounding_box=BoundingBox(x1=50, y1=50, x2=80, y2=80),
        polygon=[
            PolygonPoint(x=50, y=50),
            PolygonPoint(x=80, y=50),
            PolygonPoint(x=80, y=80),
            PolygonPoint(x=50, y=80),
        ],
    )
    annotated = annotate_frame(frame, [box], [mask])
    assert annotated.shape == frame.shape
    assert np.any(annotated[10:31, 10:31])
    assert np.any(annotated[55:75, 55:75])
    assert not np.any(frame)


def test_native_overlay_scales_once_into_aspect_preserved_preview():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    box = Detection(
        class_name="FIRE",
        confidence=0.93,
        bounding_box=BoundingBox(x1=480, y1=270, x2=960, y2=540),
    )
    mask = SegmentationDetection(
        class_name="ROAD_OBSTACLE",
        confidence=0.87,
        bounding_box=BoundingBox(x1=1200, y1=600, x2=1600, y2=900),
        polygon=[
            PolygonPoint(x=1200, y=600),
            PolygonPoint(x=1600, y=600),
            PolygonPoint(x=1600, y=900),
            PolygonPoint(x=1200, y=900),
        ],
    )
    annotated = annotate_frame(frame, [box], [mask])
    preview = cv2.resize(annotated, (853, 480), interpolation=cv2.INTER_AREA)

    # Native coordinates are rendered before the single 1920x1080 -> 853x480
    # resize. These probes would miss if coordinates were scaled twice.
    assert np.any(preview[120:123, 212:216])
    assert np.any(preview[310:355, 555:665])
    assert preview.shape[:2] == (480, 853)
    assert not np.any(frame)


def test_frozen_model_wrappers_reject_empty_input_before_loading_weights():
    with pytest.raises(DetectorInferenceError, match="empty frame"):
        YOLODetector(get_vision_config()).detect(None)
    with pytest.raises(SegmentationInferenceError, match="empty frame"):
        YOLOSegmentation(get_vision_config()).segment(None)


def test_ai_display_setting_requires_preview_and_blocks_decision_pipeline():
    with pytest.raises(ValueError, match="requires the shared camera preview"):
        Settings(_env_file=None, vision_ai_display_enabled=True)
    with pytest.raises(ValueError, match="decision pipeline"):
        Settings(
            _env_file=None,
            vision_preview_enabled=True,
            vision_ai_display_enabled=True,
            vision_live_enabled=True,
        )


def test_display_cadence_and_overlay_validity_are_bounded():
    with pytest.raises(ValueError, match="VISION_AI_DISPLAY_TARGET_FPS"):
        Settings(_env_file=None, vision_ai_display_target_fps=0.1)
    with pytest.raises(ValueError, match="VISION_AI_OVERLAY_VALID_SECONDS"):
        Settings(_env_file=None, vision_ai_overlay_valid_seconds=8.0)


def test_ai_presentation_policy_rejects_raw_alternation_stale_and_out_of_order_frames():
    base = datetime.now(timezone.utc)
    policy = AIFramePresentationPolicy(valid_seconds=1.5)
    assert policy.allow_raw_fallback()
    assert policy.overlay_state(base) == "warming"

    assert policy.accept_ai(
        sequence=5,
        frame_id="ai-5",
        timestamp=base,
        geometry_version="crop-a",
        now=base,
    )
    assert not policy.allow_raw_fallback()
    assert policy.overlay_state(base + timedelta(seconds=0.5)) == "processing"

    # Repeated and out-of-order results cannot replace a newer overlay.
    assert not policy.accept_ai(
        sequence=5,
        frame_id="ai-5-repeat",
        timestamp=base + timedelta(seconds=0.1),
        geometry_version="crop-a",
        now=base + timedelta(seconds=0.1),
    )
    assert not policy.accept_ai(
        sequence=4,
        frame_id="ai-4",
        timestamp=base + timedelta(seconds=0.2),
        geometry_version="crop-a",
        now=base + timedelta(seconds=0.2),
    )
    assert policy.overlay_state(base + timedelta(seconds=1.6)) == "stale"

    # A fresh inference result, including an empty/object-moved result or a
    # changed crop, is a new synchronized composite and replaces the old one.
    assert policy.accept_ai(
        sequence=6,
        frame_id="ai-6-empty-or-moved",
        timestamp=base + timedelta(seconds=2),
        geometry_version="crop-b",
        now=base + timedelta(seconds=2),
    )
    assert policy.geometry_version == "crop-b"
    assert policy.last_frame_id == "ai-6-empty-or-moved"


def test_inference_cpu_thread_limit_is_bounded_and_runtime_applies_it():
    with pytest.raises(ValueError, match="VISION_INFERENCE_CPU_THREADS"):
        Settings(_env_file=None, vision_inference_cpu_threads=0)
    with pytest.raises(ValueError, match="VISION_INFERENCE_CPU_THREADS"):
        Settings(_env_file=None, vision_inference_cpu_threads=17)

    class FakeCuda:
        @staticmethod
        def is_available():
            return False

    class FakeTorch:
        cuda = FakeCuda()
        cpu_threads = 8
        interop_threads = 8

        @classmethod
        def set_num_threads(cls, value):
            cls.cpu_threads = value

        @classmethod
        def set_num_interop_threads(cls, value):
            cls.interop_threads = value

        @classmethod
        def get_num_threads(cls):
            return cls.cpu_threads

        @classmethod
        def get_num_interop_threads(cls):
            return cls.interop_threads

    with patch("app.vision.inference_display.torch", FakeTorch, create=True):
        # The function imports torch locally; inject it through sys.modules.
        import sys

        previous = sys.modules.get("torch")
        sys.modules["torch"] = FakeTorch
        try:
            result = configure_torch_runtime(2)
        finally:
            if previous is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = previous

    assert result == {
        "cuda_available": False,
        "device": "cpu",
        "cpu_threads": 2,
        "interop_threads": 2,
    }
    with pytest.raises(ValueError, match="decision pipeline"):
        Settings(
            _env_file=None,
            vision_preview_enabled=True,
            vision_ai_display_enabled=True,
            vision_publish_evidence_enabled=True,
        )


def test_inference_device_auto_selects_cuda_when_available(monkeypatch):
    import sys

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True)
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert resolve_inference_device("auto") == 0
    assert resolve_inference_device("cuda:1") == "cuda:1"
    assert resolve_inference_device("cpu") == "cpu"


def test_inference_device_auto_falls_back_to_cpu_without_cuda(monkeypatch):
    import sys

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False)
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert resolve_inference_device("auto") == "cpu"


def test_inference_device_setting_rejects_invalid_value():
    with pytest.raises(ValueError, match="VISION_INFERENCE_DEVICE"):
        Settings(_env_file=None, vision_inference_device="cuda:bad")


def test_observation_inference_never_calls_decision_or_publish_paths():
    camera = SyntheticSharedCamera()
    service = SharedVisionDisplayService(
        camera,
        config=get_vision_config(),
        detector_factory=SyntheticDetector,
        segmenter_factory=SyntheticSegmenter,
        idle_timeout_seconds=2,
    )
    with (
        patch("app.vision.pipeline.IntegratedVisionPipeline.process_one") as process_one,
        patch("app.vision.publisher.VisionEvidencePublisher.publish_detection") as publish_detection,
        patch("app.vision.publisher.VisionEvidencePublisher.publish_road") as publish_road,
    ):
        try:
            service.latest(timeout_seconds=5)
        finally:
            service.stop()
        process_one.assert_not_called()
        publish_detection.assert_not_called()
        publish_road.assert_not_called()


def test_authenticated_vision_websocket_sends_matching_ai_frame_and_disconnects_cleanly():
    from app import main
    from app.vision.inference_display import VisionDisplayFrame

    class StubDisplay:
        def __init__(self):
            self.started = False
            self.read_count = 0

        def start(self):
            self.started = True

        def status(self):
            return {"detection": "active", "segmentation": "active", "error": None}

        def latest(self, **_kwargs):
            self.read_count += 1
            if self.read_count == 2:
                raise TimeoutError("synthetic inference gap")
            if self.read_count > 2:
                raise WebSocketDisconnect()
            return VisionDisplayFrame(
                jpeg=b"\xff\xd8synthetic-ai-jpeg",
                frame_id="source-frame-1",
                timestamp=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc),
                capture_width=1920,
                capture_height=1080,
                preview_width=853,
                preview_height=480,
                sequence=1,
                detections=({"class_name": "PERSON", "confidence": 0.91},),
                segmentations=(),
                detection_status="active",
                segmentation_status="active",
                detection_fps=2.0,
                segmentation_fps=2.0,
                detection_latency_ms=80.0,
                segmentation_latency_ms=50.0,
                inference_latency_ms=130.0,
                camera_fps=20.0,
                inference_device="test-device",
            )

    expiration = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode(
        {"sub": "1", "exp": expiration},
        main.settings.jwt_secret_key,
        algorithm=main.settings.jwt_algorithm,
    )
    display = StubDisplay()
    fake_user = SimpleNamespace(id=1, role=UserRole.OPERATOR)
    db = SimpleNamespace(close=lambda: None)
    with (
        patch.object(main.settings, "vision_preview_enabled", True),
        patch.object(main.settings, "vision_ai_display_enabled", True),
        patch.object(main.settings, "cors_allowed_origins", ""),
        patch.object(main.settings, "websocket_allowed_origins", "http://127.0.0.1:8080"),
        patch.object(main, "SessionLocal", return_value=db),
        patch.object(main, "authenticate_token", return_value=fake_user),
        patch.object(main, "shared_vision_display", display),
        patch("app.vision.pipeline.IntegratedVisionPipeline.process_one") as process_one,
        patch("app.vision.publisher.VisionEvidencePublisher.publish_detection") as publish_detection,
        patch("app.vision.publisher.VisionEvidencePublisher.publish_road") as publish_road,
    ):
        client = TestClient(main.app)
        with client.websocket_connect(
            "/ws/live",
            headers={"origin": "http://127.0.0.1:8080"},
        ) as websocket:
            websocket.send_json(
                {"type": "authenticate", "channel": "vision", "view": "ai", "token": token}
            )
            assert websocket.receive_json()["event_type"] == "vision_stream_authenticated"
            metadata = websocket.receive_json()
            jpeg = websocket.receive_bytes()
            assert metadata["event_type"] == "vision_frame"
            assert metadata["payload"]["frame_id"] == "source-frame-1"
            assert metadata["payload"]["view"] == "ai-overlay"
            assert metadata["payload"]["detections"][0]["class_name"] == "PERSON"
            assert metadata["payload"]["inference_device"] == "test-device"
            assert jpeg.startswith(b"\xff\xd8")
            status = websocket.receive_json()
            assert status["event_type"] == "vision_stream_status"
            assert status["payload"]["overlay_state"] == "processing"
            assert display.read_count >= 2
        assert display.started
        process_one.assert_not_called()
        publish_detection.assert_not_called()
        publish_road.assert_not_called()


def test_vision_websocket_rejects_wrong_role_and_expired_jwt():
    from app import main

    db = SimpleNamespace(close=lambda: None)
    client = TestClient(main.app)
    shared_patches = (
        patch.object(main.settings, "vision_preview_enabled", True),
        patch.object(main.settings, "vision_ai_display_enabled", True),
        patch.object(main.settings, "cors_allowed_origins", ""),
        patch.object(main.settings, "websocket_allowed_origins", "http://127.0.0.1:8080"),
        patch.object(main, "SessionLocal", return_value=db),
    )
    with shared_patches[0], shared_patches[1], shared_patches[2], shared_patches[3], shared_patches[4]:
        valid_token = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            main.settings.jwt_secret_key,
            algorithm=main.settings.jwt_algorithm,
        )
        with patch.object(main, "authenticate_token", return_value=SimpleNamespace(id=1, role=UserRole.RISK_PLANNER)):
            with client.websocket_connect("/ws/live", headers={"origin": "http://127.0.0.1:8080"}) as websocket:
                websocket.send_json({"type": "authenticate", "channel": "vision", "token": valid_token})
                with pytest.raises(WebSocketDisconnect):
                    websocket.receive_text()

        expired_token = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
            main.settings.jwt_secret_key,
            algorithm=main.settings.jwt_algorithm,
        )
        with patch.object(main, "authenticate_token", return_value=SimpleNamespace(id=1, role=UserRole.OPERATOR)):
            with client.websocket_connect("/ws/live", headers={"origin": "http://127.0.0.1:8080"}) as websocket:
                websocket.send_json({"type": "authenticate", "channel": "vision", "token": expired_token})
                with pytest.raises(WebSocketDisconnect):
                    websocket.receive_text()
