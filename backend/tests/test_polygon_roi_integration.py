from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from app.core.config import Settings
from app.severity.policies import calculate_severity
from app.vision.capture import CapturedFrame, VisionCaptureService, _capture_backend_code
from app.vision.config import get_vision_config
from app.vision.hazard import evaluate_person_in_hazard
from app.vision.occupancy import calculate_road_occupancy
from app.vision.pipeline import IntegratedVisionPipeline, VisionIntegrationError
from app.vision.polygon_roi import (
    PolygonRegion,
    board_to_raw_point,
    load_polygon_roi_config,
    polygon_area,
    raw_to_board_point,
)
from app.vision.schemas import (
    BoundingBox,
    CoordinateSystem,
    Detection,
    FrameMetadata,
    FrameSourceType,
    PolygonPoint,
    PolygonROI,
    ROI,
    RoadSegmentationResult,
    SegmentationDetection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE_A_DRAFT = PROJECT_ROOT / "reports" / "debug" / "camera_alignment" / "roi_calibration_phase_a_draft.json"


def _captured_frame() -> CapturedFrame:
    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
    metadata = FrameMetadata(
        frame_id="polygon-fixture",
        timestamp=datetime(2026, 10, 22, tzinfo=timezone.utc),
        source=FrameSourceType.CAMERA,
        width=1920,
        height=1080,
    )
    return CapturedFrame(frame=frame, metadata=metadata)


class _Capture:
    def capture_one(self):
        return _captured_frame()

    def close(self):
        self.closed = True


class _Detector:
    last_inference_duration_ms = 1.0
    last_inference_per_second = 1000.0

    def __init__(self, detections=None):
        self.detections = detections or []

    def detect(self, _frame):
        return self.detections


class _Segmenter:
    last_inference_duration_ms = 1.0
    last_inference_per_second = 1000.0

    def __init__(self, segmentations=None):
        self.segmentations = segmentations or []

    def segment(self, _frame):
        return self.segmentations


class _Publisher:
    def __init__(self):
        self.detections = []
        self.roads = []

    def publish_detection(self, *args):
        self.detections.append(args)

    def publish_road(self, *args):
        self.roads.append(args)


class PolygonROILoaderTests(unittest.TestCase):
    def test_polygon_mode_and_new_camera_options_preserve_defaults(self):
        defaults = {name: field.default for name, field in Settings.model_fields.items()}
        self.assertFalse(defaults["vision_polygon_roi_enabled"])
        self.assertIsNone(defaults["vision_polygon_roi_config_path"])
        self.assertIsNone(defaults["vision_camera_index"])
        self.assertIsNone(defaults["vision_capture_backend"])
        self.assertIsNone(defaults["vision_capture_fourcc"])
        self.assertFalse(defaults["vision_live_enabled"])
        self.assertFalse(defaults["vision_publish_evidence_enabled"])

    def test_loads_draft_and_translates_coordinates_once_reversibly(self):
        config = load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))
        self.assertEqual((config.crop.x, config.crop.y, config.crop.width, config.crop.height), (408, 66, 1134, 848))
        raw_point = (1055.0, 575.0)
        board_point = raw_to_board_point(raw_point, (config.crop.x, config.crop.y))
        self.assertEqual(board_point, (647.0, 509.0))
        self.assertEqual(board_to_raw_point(board_point, (config.crop.x, config.crop.y)), raw_point)
        self.assertEqual(config.status, "DRAFT_NOT_PRODUCTION_ACTIVE")

    def test_rejects_wrong_resolution_self_intersection_and_clipped_crop_boundary(self):
        with self.assertRaisesRegex(ValueError, "expected 1280x720"):
            load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1280, 720))

        source = json.loads(PHASE_A_DRAFT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.json"
            broken = json.loads(json.dumps(source))
            building = next(item for item in broken["regions"] if item["role"] == "building_detection_roi")
            building["points"] = [[900, 430], [1200, 680], [900, 680], [1200, 430]]
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "self-intersecting"):
                load_polygon_roi_config(path, expected_resolution=(1920, 1080))

            clipped = json.loads(json.dumps(source))
            crop = next(item for item in clipped["regions"] if item["role"] == "processing_crop")
            crop["points"] = [[430, 90], [1518, 90], [1518, 890], [430, 890]]
            path.write_text(json.dumps(clipped), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not contained by processing_crop"):
                load_polygon_roi_config(path, expected_resolution=(1920, 1080))

    def test_rejects_nonempty_unconfirmed_routing_mapping(self):
        source = json.loads(PHASE_A_DRAFT.read_text(encoding="utf-8"))
        source["routing_edge_mappings"] = [{"region_id": "road_upper_horizontal_candidate", "edge_id": "edge-1"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapped.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mappings empty"):
                load_polygon_roi_config(path, expected_resolution=(1920, 1080))

    def test_saved_draft_round_trips_through_versioned_loader(self):
        source = json.loads(PHASE_A_DRAFT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved-draft.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            loaded = load_polygon_roi_config(path, expected_resolution=(1920, 1080))
        self.assertEqual(loaded.crop.x, 408)
        self.assertEqual([region.label for region in loaded.road_segments], ["S1", "S2", "S3"])

    def test_unmapped_road_ir_pair_remains_not_evaluated(self):
        from app.vision.sync import _evaluate_pair

        timestamp = datetime.now(timezone.utc)
        road = SimpleNamespace(
            road_roi_name="S1",
            frame=SimpleNamespace(timestamp=timestamp),
        )
        evidence = _evaluate_pair(
            road=road,
            ir_sensor=None,
            ir_state=None,
            occupancy_threshold=0.2,
            ir_value_threshold=1.0,
        )
        self.assertIsNone(evidence.conflict)
        self.assertIn("mapping is not configured", evidence.conflict_reason)

    def test_camera_backend_selection_and_fourcc_request_order(self):
        config = replace(
            get_vision_config(),
            source="CAMERA",
            camera_index=0,
            capture_backend="DSHOW",
            capture_fourcc="MJPG",
            frame_width=1920,
            frame_height=1080,
        )
        self.assertEqual(_capture_backend_code("CAP_DSHOW"), _capture_backend_code("DSHOW"))
        calls = []

        class FakeCapture:
            def isOpened(self):
                return True

            def set(self, prop, value):
                calls.append(("set", prop, value))
                return True

            def get(self, prop):
                values = {
                    cv2.CAP_PROP_FRAME_WIDTH: 1920,
                    cv2.CAP_PROP_FRAME_HEIGHT: 1080,
                    cv2.CAP_PROP_FPS: 20.0,
                    cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
                }
                return values.get(prop, 0.0)

            def getBackendName(self):
                return "DSHOW"

            def release(self):
                calls.append(("release",))

        def make_capture(*args):
            calls.append(("open", *args))
            return FakeCapture()

        service = VisionCaptureService(config)
        with patch("app.vision.capture.cv2.VideoCapture", side_effect=make_capture):
            service.open()
            service.close()
        self.assertEqual(calls[0], ("open", 0, _capture_backend_code("DSHOW")))
        self.assertEqual(
            [call[1] for call in calls if call[0] == "set"],
            [cv2.CAP_PROP_FOURCC, cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT],
        )
        self.assertEqual(calls[-1], ("release",))


class PolygonPipelineTests(unittest.TestCase):
    def _pipeline(self, detections=None, segmentations=None, *, enabled=True, path=PHASE_A_DRAFT):
        config = replace(
            get_vision_config(),
            source="CAMERA",
            frame_width=1920,
            frame_height=1080,
            polygon_roi_enabled=enabled,
            polygon_roi_config_path=str(path),
        )
        publisher = _Publisher()
        pipeline = IntegratedVisionPipeline(
            config=config,
            capture=_Capture(),
            detector=_Detector(detections),
            segmenter=_Segmenter(segmentations),
            publisher=publisher,
        )
        return pipeline, publisher

    def test_polygon_mode_filters_building_and_evaluates_distinct_hazard_polygon(self):
        inside_hazard = Detection(
            class_name="PERSON",
            confidence=0.91,
            bounding_box=BoundingBox(x1=630, y1=490, x2=664, y2=528),
        )
        inside_building_outside_hazard = Detection(
            class_name="PERSON",
            confidence=0.88,
            bounding_box=BoundingBox(x1=486, y1=370, x2=520, y2=398),
        )
        pipeline, publisher = self._pipeline([inside_hazard, inside_building_outside_hazard])
        processed = pipeline.process_one(publish=False)
        self.assertEqual(processed.board_frame.shape[:2], (848, 1134))
        self.assertEqual(len(processed.detection_result.detections), 2)
        self.assertEqual(processed.detection_result.hazard_polygon.name, "HAZARD AREA")
        self.assertTrue(processed.detection_result.person_in_hazard)
        self.assertEqual(processed.person_hazard.matched_person_indexes, [0])
        self.assertEqual(publisher.detections, [])
        self.assertEqual(publisher.roads, [])

    def test_hazard_polygon_critical_override_remains_intact(self):
        config = load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))
        hazard = config.hazard.as_polygon_roi()
        person = Detection(
            class_name="person",
            confidence=0.8,
            bounding_box=BoundingBox(x1=630, y1=490, x2=664, y2=528),
        )
        result = calculate_severity(detections=[person], hazard_zone=hazard)
        self.assertEqual(result.status, "critical_override")
        self.assertTrue(result.critical_override)

    def test_building_area_and_person_hazard_polygon_are_used_separately(self):
        config = load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))
        building = config.building.as_polygon_roi()
        hazard = config.hazard.as_polygon_roi()
        fire = Detection(
            class_name="fire",
            confidence=0.9,
            bounding_box=BoundingBox(x1=600, y1=470, x2=620, y2=490),
        )
        result = calculate_severity(
            detections=[fire],
            hazard_zone=hazard,
            building_roi=building,
        )
        self.assertAlmostEqual(result.a_score, 400 / polygon_area([(p.x, p.y) for p in building.points]))
        self.assertNotAlmostEqual(
            result.a_score,
            400 / polygon_area([(p.x, p.y) for p in hazard.points]),
        )

    def test_road_pixel_masks_are_exclusive_and_s2_claims_shared_junction(self):
        config = load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))
        masks = config.road_masks((config.crop.height, config.crop.width, 3))
        by_id = {mask.region.region_id: mask.valid_mask for mask in masks}
        vertical = by_id["road_main_vertical_candidate"]
        upper = by_id["road_upper_horizontal_candidate"]
        x, y = raw_to_board_point((832, 220), (config.crop.x, config.crop.y))
        self.assertEqual(vertical[round(y), round(x)], 1)
        self.assertEqual(upper[round(y), round(x)], 0)
        total_claimed = np.zeros_like(vertical)
        for mask_result in masks:
            mask = mask_result.valid_mask
            self.assertFalse(np.any((total_claimed != 0) & (mask != 0)))
            total_claimed |= mask
        self.assertEqual(config.junction_owner_region_id, "road_main_vertical_candidate")

    def test_exclusion_mask_removes_only_allowed_road_pixels(self):
        config = load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))
        region = PolygonRegion(
            region_id="test_support_overlap",
            label="TEST EXCLUSION",
            raw_points=((500, 800), (550, 800), (550, 850), (500, 850)),
            board_points=tuple(
                raw_to_board_point(point, (config.crop.x, config.crop.y))
                for point in ((500, 800), (550, 800), (550, 850), (500, 850))
            ),
        )
        with_exclusion = replace(config, exclusions=(*config.exclusions, region))
        original_masks = config.road_masks((config.crop.height, config.crop.width, 3))
        excluded_masks = with_exclusion.road_masks((config.crop.height, config.crop.width, 3))
        sample_x, sample_y = raw_to_board_point((520, 820), (config.crop.x, config.crop.y))
        s3_id = "road_lower_horizontal_candidate"
        original = next(mask.valid_mask for mask in original_masks if mask.region.region_id == s3_id)
        excluded = next(mask.valid_mask for mask in excluded_masks if mask.region.region_id == s3_id)
        self.assertEqual(original[round(sample_y), round(sample_x)], 1)
        self.assertEqual(excluded[round(sample_y), round(sample_x)], 0)

    def test_occupancy_denominator_and_pixels_use_valid_mask_only(self):
        frame = FrameMetadata(
            frame_id="occupancy-mask",
            timestamp=datetime.now(timezone.utc),
            source=FrameSourceType.CAMERA,
            width=30,
            height=30,
            coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
        )
        valid_mask = np.zeros((30, 30), dtype=np.uint8)
        valid_mask[8:18, 10:20] = 1
        valid_mask[8:13, 10:20] = 0
        road = RoadSegmentationResult(
            frame=frame,
            road_roi_name="S1",
            road_roi=ROI(name="S1", x=10, y=8, width=10, height=10),
            segmentations=[
                SegmentationDetection(
                    class_name="ROAD_OBSTACLE",
                    confidence=0.9,
                    bounding_box=BoundingBox(x1=10, y1=8, x2=19, y2=17),
                    polygon=[
                        PolygonPoint(x=10, y=8),
                        PolygonPoint(x=19, y=8),
                        PolygonPoint(x=19, y=17),
                        PolygonPoint(x=10, y=17),
                    ],
                )
            ],
            processing_timestamp=datetime.now(timezone.utc),
            valid_road_mask=valid_mask,
        )
        result = calculate_road_occupancy(road)
        self.assertEqual(result.roi_pixels, 50)
        self.assertEqual(result.occupied_pixels, 50)
        self.assertEqual(result.occupancy_ratio, 1.0)

    def test_invalid_opt_in_config_fails_closed_but_disabled_mode_uses_rectangles(self):
        config = replace(
            get_vision_config(),
            source="CAMERA",
            polygon_roi_enabled=True,
            polygon_roi_config_path=str(PHASE_A_DRAFT) + ".missing",
        )
        with self.assertRaisesRegex(VisionIntegrationError, "Invalid opt-in polygon ROI config"):
            IntegratedVisionPipeline(config=config)

        pipeline, _publisher = self._pipeline(enabled=False, path=Path("not-a-real-config.json"))
        processed = pipeline.process_one(publish=False)
        self.assertEqual((processed.result.board_crop.x, processed.result.board_crop.y), (340, 80))
        self.assertIsNone(processed.result.building_polygon)
        self.assertIsNone(processed.detection_result.person_in_hazard)


if __name__ == "__main__":
    unittest.main()
