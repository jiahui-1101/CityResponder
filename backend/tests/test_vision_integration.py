from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.events.models import Event
from app.events.repository import append_event
from app.evidence.service import EvidenceLimitReached, retain_incident_evidence_frame
from app.evidence.store import LocalEvidenceFrameStore
from app.vision.capture import CapturedFrame, CaptureReadError
from app.vision.config import get_vision_config
from app.vision.model_contract import (
    ModelContractError,
    resolve_weights_path,
    validate_model_contract,
)
from app.vision.pipeline import IntegratedVisionPipeline, VisionIntegrationError
from app.vision.schemas import (
    BoundingBox,
    CoordinateSystem,
    Detection,
    FrameMetadata,
    FrameSourceType,
    PolygonPoint,
    SegmentationDetection,
)


class FakeModel:
    def __init__(self, task: str, names: dict[int, str]) -> None:
        self.task = task
        self.names = names


class FakeCapture:
    def __init__(self, captured: CapturedFrame | None = None, error: Exception | None = None) -> None:
        self.captured = captured
        self.error = error
        self.closed = False

    def capture_one(self) -> CapturedFrame | None:
        if self.error:
            raise self.error
        return self.captured

    def close(self) -> None:
        self.closed = True


class FakeDetector:
    last_inference_duration_ms = 10.0
    last_inference_per_second = 100.0

    def __init__(self, detections: list[Detection] | None = None, error: Exception | None = None) -> None:
        self.detections = detections or []
        self.error = error

    def detect(self, _frame: np.ndarray) -> list[Detection]:
        if self.error:
            raise self.error
        return self.detections


class FakeSegmenter:
    last_inference_duration_ms = 20.0
    last_inference_per_second = 50.0

    def __init__(self, items: list[SegmentationDetection] | None = None) -> None:
        self.items = items or []

    def segment(self, _frame: np.ndarray) -> list[SegmentationDetection]:
        return self.items


class FakePublisher:
    def __init__(self) -> None:
        self.detection_calls = []
        self.road_calls = []

    def publish_detection(self, result, person_hazard=None) -> None:
        self.detection_calls.append((result, person_hazard))

    def publish_road(self, result) -> None:
        self.road_calls.append(result)


def config():
    return replace(
        get_vision_config(),
        source="CAMERA",
        camera_index=1,
        frame_width=1920,
        frame_height=1080,
        require_exact_frame_size=True,
        board_crop_coordinates=(
            '{"name":"raw_board_crop","x":340,"y":80,"width":1080,"height":840}'
        ),
        building_roi_coordinates=(
            '{"name":"building_a","x":460,"y":350,"width":340,"height":360}'
        ),
        road_roi_coordinates=(
            '[{"name":"road_main","x":10,"y":675,"width":1035,"height":145}]'
        ),
    )


def captured_frame() -> CapturedFrame:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    metadata = FrameMetadata(
        frame_id="fixture-1",
        timestamp=datetime(2026, 10, 4, tzinfo=timezone.utc),
        source=FrameSourceType.CAMERA,
        width=1920,
        height=1080,
    )
    return CapturedFrame(frame=frame, metadata=metadata)


def road_polygon() -> SegmentationDetection:
    return SegmentationDetection(
        class_name="ROAD_OBSTACLE",
        confidence=0.88,
        bounding_box=BoundingBox(x1=100, y1=700, x2=180, y2=760),
        polygon=[
            PolygonPoint(x=100, y=700),
            PolygonPoint(x=180, y=700),
            PolygonPoint(x=180, y=760),
            PolygonPoint(x=100, y=760),
        ],
    )


class VisionIntegrationTests(unittest.TestCase):
    def make_pipeline(self, *, detections=None, segmentations=None, capture=None, detector=None):
        publisher = FakePublisher()
        pipeline = IntegratedVisionPipeline(
            config=config(),
            capture=capture or FakeCapture(captured_frame()),
            detector=detector or FakeDetector(detections),
            segmenter=FakeSegmenter(segmentations),
            publisher=publisher,
        )
        return pipeline, publisher

    def test_model_contract_accepts_expected_detection_mapping(self):
        validate_model_contract(
            FakeModel("detect", {0: "fire", 1: "smoke", 2: "person"}),
            expected_task="detect",
            expected_classes=("fire", "smoke", "person"),
            weights_path=Path("fixture.pt"),
        )

    def test_model_contract_rejects_wrong_task_or_classes(self):
        with self.assertRaises(ModelContractError):
            validate_model_contract(
                FakeModel("segment", {0: "fire"}),
                expected_task="detect",
                expected_classes=("fire", "smoke", "person"),
                weights_path=Path("fixture.pt"),
            )

    def test_model_unavailable_fails_clearly(self):
        with self.assertRaisesRegex(ModelContractError, "do not exist"):
            resolve_weights_path("missing/frozen-model.pt")

    def test_locked_board_crop_is_applied_in_raw_camera_coordinates(self):
        pipeline, _ = self.make_pipeline()
        processed = pipeline.process_one(publish=False)
        self.assertEqual(processed.board_frame.shape[:2], (840, 1080))
        self.assertEqual(processed.result.raw_frame.coordinate_system, CoordinateSystem.RAW_CAMERA)
        self.assertEqual(processed.result.frame.coordinate_system, CoordinateSystem.RAW_BOARD_CROP)
        self.assertEqual((processed.result.frame.crop_origin_x, processed.result.frame.crop_origin_y), (340, 80))

    def test_building_a_filters_fusion_detection_by_box_center(self):
        inside = Detection(
            class_name="FIRE",
            confidence=0.91,
            bounding_box=BoundingBox(x1=500, y1=400, x2=560, y2=470),
        )
        outside = Detection(
            class_name="PERSON",
            confidence=0.82,
            bounding_box=BoundingBox(x1=50, y1=50, x2=100, y2=130),
        )
        pipeline, _ = self.make_pipeline(detections=[inside, outside])
        processed = pipeline.process_one(publish=False)
        self.assertEqual(len(processed.result.detections), 2)
        self.assertEqual(processed.detection_result.detections, [inside])
        self.assertEqual(processed.detection_result.building_roi.name, "building_a")

    def test_road_roi_preserves_polygon_and_calculates_occupancy(self):
        outside = SegmentationDetection(
            class_name="POTHOLE",
            confidence=0.72,
            bounding_box=BoundingBox(x1=500, y1=200, x2=550, y2=250),
            polygon=[
                PolygonPoint(x=500, y=200),
                PolygonPoint(x=550, y=200),
                PolygonPoint(x=550, y=250),
            ],
        )
        pipeline, _ = self.make_pipeline(segmentations=[road_polygon(), outside])
        processed = pipeline.process_one(publish=False)
        road = processed.road_evidence[0]
        self.assertEqual(len(road.raw_segmentations), 1)
        self.assertGreater(road.occupancy_ratio, 0)
        self.assertEqual(road.raw_segmentations[0].polygon, road_polygon().polygon)

    def test_structured_output_contains_models_confidence_timestamp_and_frame(self):
        detection = Detection(
            class_name="SMOKE",
            confidence=0.77,
            bounding_box=BoundingBox(x1=500, y1=400, x2=560, y2=470),
        )
        pipeline, _ = self.make_pipeline(detections=[detection], segmentations=[road_polygon()])
        result = pipeline.process_one(publish=False).result
        self.assertEqual(result.frame.frame_id, "fixture-1:board")
        self.assertEqual(result.detections[0].confidence, 0.77)
        self.assertEqual(result.detection_model.version, "cityresponder_detection_v2")
        self.assertEqual(result.segmentation_model.version, "cityresponder_segmentation_v1")

    def test_empty_scene_is_valid_evidence_not_a_failure_substitute(self):
        pipeline, _ = self.make_pipeline()
        processed = pipeline.process_one(publish=False)
        self.assertEqual(processed.result.detections, [])
        self.assertEqual(processed.result.segmentations, [])
        self.assertEqual(processed.road_evidence[0].occupancy_ratio, 0)

    def test_camera_read_failure_raises_and_publishes_nothing(self):
        capture = FakeCapture(error=CaptureReadError("fixture read failure"))
        pipeline, publisher = self.make_pipeline(capture=capture)
        with self.assertRaises(VisionIntegrationError):
            pipeline.process_one()
        self.assertEqual(publisher.detection_calls, [])
        self.assertEqual(publisher.road_calls, [])

    def test_inference_failure_raises_and_publishes_nothing(self):
        detector = FakeDetector(error=RuntimeError("fixture inference failure"))
        pipeline, publisher = self.make_pipeline(detector=detector)
        with self.assertRaises(VisionIntegrationError):
            pipeline.process_one()
        self.assertEqual(publisher.detection_calls, [])
        self.assertEqual(publisher.road_calls, [])

    def test_pipeline_publishes_only_vision_evidence_not_actuator_commands(self):
        pipeline, publisher = self.make_pipeline(segmentations=[road_polygon()])
        pipeline.process_one(publish=True)
        self.assertEqual(len(publisher.detection_calls), 1)
        self.assertEqual(len(publisher.road_calls), 1)
        self.assertFalse(hasattr(pipeline, "dispatch"))

    def test_rendering_does_not_persist_continuous_video(self):
        pipeline, _ = self.make_pipeline(segmentations=[road_polygon()])
        processed = pipeline.process_one(publish=False)
        with tempfile.TemporaryDirectory() as directory:
            before = list(Path(directory).iterdir())
            encoded, metadata = pipeline.render_annotated_frame(processed)
            after = list(Path(directory).iterdir())
        self.assertTrue(encoded.startswith(b"\xff\xd8"))
        self.assertEqual(before, after)
        self.assertEqual(metadata["frame_id"], "fixture-1:board")

    def test_evidence_retention_rejects_sixth_frame(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[Event.__table__])
        with Session(engine) as db, tempfile.TemporaryDirectory() as directory:
            decision_id = "fixture-incident"
            append_event(
                db,
                event_type="incident_decision",
                entity_type="incident",
                entity_id=decision_id,
                payload={"decision_id": decision_id},
            )
            store = LocalEvidenceFrameStore(Path(directory))
            for index in range(5):
                retain_incident_evidence_frame(
                    db,
                    decision_id=decision_id,
                    selected_frame=b"jpeg",
                    frame_index=index,
                    content_type="image/jpeg",
                    captured_at=datetime.now(timezone.utc),
                    annotation_metadata={"frame": index},
                    store=store,
                )
            with self.assertRaises(EvidenceLimitReached):
                retain_incident_evidence_frame(
                    db,
                    decision_id=decision_id,
                    selected_frame=b"jpeg",
                    frame_index=5,
                    content_type="image/jpeg",
                    captured_at=datetime.now(timezone.utc),
                    annotation_metadata={"frame": 5},
                    store=store,
                )


if __name__ == "__main__":
    unittest.main()
