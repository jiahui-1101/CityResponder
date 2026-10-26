"""Deterministic invariants for the camera-only realignment draft.

These checks load saved images/configuration only. They do not open a camera,
run YOLO, rerun T0-T7, or invoke routing, MQTT, dispatch, or actuators.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

import cv2
import numpy as np

from app.vision.polygon_roi import (
    board_to_raw_point,
    load_polygon_roi_config,
    rasterize_polygon,
    raw_to_board_point,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALIGNMENT_DIR = PROJECT_ROOT / "reports" / "debug" / "camera_alignment"
SOURCE_ROI = ALIGNMENT_DIR / "roi_calibration_phase_a_draft.json"
REALIGNED_ROI = ALIGNMENT_DIR / "roi_calibration_phase_a_realigned_draft.json"
SOURCE_GRAPH = ALIGNMENT_DIR / "road_graph_phase_b1_draft.json"
REALIGNED_GRAPH = ALIGNMENT_DIR / "road_graph_phase_b1_realigned_draft.json"
FINAL_REVIEW_ROI = ALIGNMENT_DIR / "roi_calibration_phase_a_final_review_draft.json"
FINAL_REVIEW_GRAPH = ALIGNMENT_DIR / "road_graph_phase_b1_final_review_draft.json"
LATEST_RAW_FRAME = ALIGNMENT_DIR / "camera_alignment_20261025T084211_819245Z_index0_raw.jpg"
HISTORICAL_MANIFEST = ALIGNMENT_DIR / "historical_t0_t7_sha256.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply(matrix: list[list[float]], point: list[float] | tuple[float, float]) -> tuple[float, float]:
    x, y = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    )


def _assert_transformed_points(testcase, before, after, matrix, *, places: int = 2):
    testcase.assertEqual(len(before), len(after))
    for source, target in zip(before, after):
        expected = _apply(matrix, source)
        testcase.assertAlmostEqual(target[0], expected[0], places=places)
        testcase.assertAlmostEqual(target[1], expected[1], places=places)


def _normalize_graph_semantics(graph: dict) -> dict:
    normalized = copy.deepcopy(graph)
    for key in (
        "reference_image",
        "phase_a_roi_draft",
        "camera_reference",
        "camera_realignment",
        "last_updated_by",
        "last_updated_at_utc",
    ):
        normalized.pop(key, None)

    def normalize_raw_point(value):
        if isinstance(value, dict):
            if value.get("coordinate_system") == "RAW_CAMERA" and "x" in value and "y" in value:
                value["x"] = value["y"] = "<transformed-camera-coordinate>"
            for child in value.values():
                normalize_raw_point(child)
        elif isinstance(value, list):
            for child in value:
                normalize_raw_point(child)

    for node in normalized.get("nodes", []):
        normalize_raw_point(node.get("position", {}))
    for edge in normalized.get("edges", []):
        centerline = edge.get("centerline", {})
        for point in centerline.get("points", []):
            point["x"] = point["y"] = "<transformed-camera-coordinate>"
        normalize_raw_point(edge.get("possible_barriers", []))
    normalize_raw_point(normalized.get("endpoints", {}))
    return normalized


class TestCameraRealignmentDraft(unittest.TestCase):
    def test_final_review_s1_endpoint_follows_asphalt_and_other_roi_geometry_is_unchanged(self):
        previous = _json(REALIGNED_ROI)
        final = _json(FINAL_REVIEW_ROI)
        self.assertEqual(final["status"], "DRAFT_NOT_PRODUCTION_ACTIVE")
        self.assertEqual(final["reference_image"], str(LATEST_RAW_FRAME.resolve()))
        prior_regions = {r["region_id"]: r for r in previous["regions"]}
        final_regions = {r["region_id"]: r for r in final["regions"]}
        self.assertEqual(set(prior_regions), set(final_regions))
        for region_id, before in prior_regions.items():
            after = final_regions[region_id]
            self.assertEqual(before["role"], after["role"])
            if region_id != "road_upper_horizontal_candidate":
                self.assertEqual(before["points"], after["points"], region_id)
                self.assertEqual(before.get("initial_points"), after.get("initial_points"), region_id)
            if before["role"] == "exclusion_mask":
                self.assertEqual(after["status"], "DRAFT_REVIEWED_PENDING_OPERATOR_APPROVAL")
        s1 = final_regions["road_upper_horizontal_candidate"]
        self.assertEqual(s1["points"], [[762.353, 151.849], [1421.0, 166.0], [1424.0, 267.0], [760.349, 262.725]])
        self.assertEqual(s1["initial_points"], prior_regions["road_upper_horizontal_candidate"]["initial_points"])

        gray = cv2.imread(str(LATEST_RAW_FRAME), cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(gray)
        for y, expected_last_x in ((219, 1419), (260, 1424), (266, 1424), (267, 1419)):
            dark_x = [x for x in range(1400, 1450) if gray[y, x] < 130]
            self.assertTrue(dark_x, f"expected road pixels in sampled row {y}")
            self.assertEqual(max(dark_x), expected_last_x, f"row {y}")
        self.assertFalse(any(gray[268, x] < 130 for x in range(1400, 1450)))

        config = load_polygon_roi_config(FINAL_REVIEW_ROI, expected_resolution=(1920, 1080))
        self.assertEqual((config.crop.x, config.crop.y, config.crop.width, config.crop.height), (325, 26, 1149, 868))
        masks = config.road_masks((config.crop.height, config.crop.width, 3))
        self.assertEqual(
            [m.region.region_id for m in masks],
            [
                "road_main_vertical_candidate",
                "road_upper_horizontal_candidate",
                "road_lower_horizontal_candidate",
            ],
        )
        for left, right in ((masks[0], masks[1]), (masks[0], masks[2]), (masks[1], masks[2])):
            self.assertFalse(np.any((left.valid_mask != 0) & (right.valid_mask != 0)))
        for exclusion in config.exclusions:
            excluded = rasterize_polygon(exclusion.board_points, config.crop.width, config.crop.height)
            for road in masks:
                self.assertFalse(np.any((excluded != 0) & (road.valid_mask != 0)))

    def test_final_review_graph_moves_only_n3_and_pe05_endpoint_and_keeps_gate_unverified(self):
        previous = _json(REALIGNED_GRAPH)
        final = _json(FINAL_REVIEW_GRAPH)
        self.assertEqual(final["status"], previous["status"])
        self.assertEqual([n["node_id"] for n in final["nodes"]], [n["node_id"] for n in previous["nodes"]])
        self.assertEqual([e["edge_id"] for e in final["edges"]], [e["edge_id"] for e in previous["edges"]])
        self.assertEqual(final["routes"], previous["routes"])
        self.assertEqual(final["gate_control_contract"], previous["gate_control_contract"])
        self.assertEqual(final["endpoints"], previous["endpoints"])

        old_nodes = {n["node_id"]: n for n in previous["nodes"]}
        new_nodes = {n["node_id"]: n for n in final["nodes"]}
        for node_id in old_nodes:
            if node_id == "N3":
                self.assertEqual([new_nodes[node_id]["position"]["x"], new_nodes[node_id]["position"]["y"]], [1419.0, 219.172])
                expected_node = copy.deepcopy(old_nodes[node_id])
                expected_node["position"]["x"] = 1419.0
                self.assertEqual(new_nodes[node_id], expected_node)
            else:
                self.assertEqual(new_nodes[node_id], old_nodes[node_id], node_id)

        old_edges = {e["edge_id"]: e for e in previous["edges"]}
        new_edges = {e["edge_id"]: e for e in final["edges"]}
        for edge_id in old_edges:
            if edge_id != "PE05":
                self.assertEqual(new_edges[edge_id], old_edges[edge_id], edge_id)
            else:
                expected_edge = copy.deepcopy(old_edges[edge_id])
                expected_edge["centerline"]["points"][-1]["x"] = 1419.0
                self.assertEqual(new_edges[edge_id], expected_edge)
                endpoint = new_edges[edge_id]["centerline"]["points"][-1]
                self.assertEqual([endpoint["x"], endpoint["y"]], [new_nodes["N3"]["position"]["x"], new_nodes["N3"]["position"]["y"]])
        pe07_previous = old_edges["PE07"]["possible_barriers"]
        pe07_final = new_edges["PE07"]["possible_barriers"]
        self.assertEqual(pe07_final, pe07_previous)
        self.assertIn("POSITION_UNVERIFIED", pe07_final[0]["status"])

    def test_realigned_roi_loads_in_raw_camera_coordinates_and_preserves_crop_conversion(self):
        config = load_polygon_roi_config(REALIGNED_ROI, expected_resolution=(1920, 1080))
        self.assertEqual(config.status, "DRAFT_NOT_PRODUCTION_ACTIVE")
        self.assertEqual((config.crop.x, config.crop.y, config.crop.width, config.crop.height), (325, 26, 1149, 868))
        raw = (1200.25, 400.5)
        board = raw_to_board_point(raw, (config.crop.x, config.crop.y))
        self.assertEqual(board_to_raw_point(board, (config.crop.x, config.crop.y)), raw)

    def test_roi_identities_and_board_anchored_polygons_follow_stored_transform(self):
        source = _json(SOURCE_ROI)
        target = _json(REALIGNED_ROI)
        matrix = target["camera_realignment"]["matrix_2x3"]
        source_regions = {item["region_id"]: item for item in source["regions"]}
        target_regions = {item["region_id"]: item for item in target["regions"]}
        self.assertEqual(set(source_regions), set(target_regions))
        width, height = 1920, 1080

        for region_id, original in source_regions.items():
            current = target_regions[region_id]
            self.assertEqual((current["role"], current["name"], current["label"]),
                             (original["role"], original["name"], original["label"]))
            for points_key in ("points", "initial_points"):
                if points_key not in original or original["role"] == "processing_crop":
                    continue
                points = current.get(points_key)
                self.assertIsNotNone(points)
                for x, y in points:
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x, width - 1)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y, height - 1)

                # These geometries are board anchored and retain exact transformed
                # vertices. The road-domain mask has a separately documented 1px
                # raster containment expansion; its initial_points retain the transform.
                if original["role"] == "exclusion_mask":
                    continue
                if original["role"] == "road_segmentation_roi" and points_key == "points":
                    continue
                _assert_transformed_points(self, original[points_key], points, matrix)

        source_domain = next(x for x in source["regions"] if x["role"] == "road_segmentation_roi")
        target_domain = next(x for x in target["regions"] if x["role"] == "road_segmentation_roi")
        _assert_transformed_points(self, source_domain["points"], target_domain["initial_points"], matrix)
        source_junctions = source["phase_a_integration"]["junction_regions_raw"]
        target_junctions = target["phase_a_integration"]["junction_regions_raw"]
        self.assertEqual([j["junction_id"] for j in source_junctions], [j["junction_id"] for j in target_junctions])
        for before, after in zip(source_junctions, target_junctions):
            self.assertEqual(before["label"], after["label"])
            _assert_transformed_points(self, before["points"], after["points"], matrix)
            for x, y in after["points"]:
                self.assertGreaterEqual(x, 0)
                self.assertLess(x, 1920)
                self.assertGreaterEqual(y, 0)
                self.assertLess(y, 1080)
        crop = next(x for x in target["regions"] if x["role"] == "processing_crop")
        self.assertEqual(crop["points"], [[325, 26], [1474, 26], [1474, 894], [325, 894]])

    def test_junction_owner_masks_are_disjoint_and_support_masks_exclude_road_pixels(self):
        old_config = load_polygon_roi_config(SOURCE_ROI, expected_resolution=(1920, 1080))
        new_config = load_polygon_roi_config(REALIGNED_ROI, expected_resolution=(1920, 1080))
        self.assertEqual(new_config.junction_owner_region_id, old_config.junction_owner_region_id)
        self.assertEqual(new_config.junction_owner_region_id, "road_main_vertical_candidate")
        masks = new_config.road_masks((new_config.crop.height, new_config.crop.width, 3))
        for index, left in enumerate(masks):
            self.assertGreater(np.count_nonzero(left.valid_mask), 0)
            for right in masks[index + 1 :]:
                self.assertFalse(np.any((left.valid_mask != 0) & (right.valid_mask != 0)))

        for exclusion in new_config.exclusions:
            exclusion_mask = rasterize_polygon(
                exclusion.board_points, new_config.crop.width, new_config.crop.height
            )
            for road in masks:
                self.assertFalse(np.any((exclusion_mask != 0) & (road.valid_mask != 0)))

        target = _json(REALIGNED_ROI)
        support_regions = [r for r in target["regions"] if r["role"] == "exclusion_mask"]
        self.assertEqual(len(support_regions), 2)
        self.assertTrue(all(r["status"] == "DRAFT_NEEDS_REVIEW" for r in support_regions))
        self.assertTrue(all("operator boundary confirmation" in r["geometry_basis"] for r in support_regions))

    def test_graph_visual_coordinates_transform_while_connectivity_routes_and_gate_contract_match(self):
        source = _json(SOURCE_GRAPH)
        target = _json(REALIGNED_GRAPH)
        matrix = target["camera_realignment"]["matrix_2x3"]
        self.assertEqual(_normalize_graph_semantics(source), _normalize_graph_semantics(target))

        source_nodes = {n["node_id"]: n for n in source["nodes"]}
        target_nodes = {n["node_id"]: n for n in target["nodes"]}
        self.assertEqual(set(source_nodes), set(target_nodes))
        for node_id in source_nodes:
            before, after = source_nodes[node_id]["position"], target_nodes[node_id]["position"]
            self.assertEqual(before.get("coordinate_system"), "RAW_CAMERA")
            _assert_transformed_points(self, [[before["x"], before["y"]]], [[after["x"], after["y"]]], matrix)
            self.assertGreaterEqual(after["x"], 0)
            self.assertLess(after["x"], 1920)
            self.assertGreaterEqual(after["y"], 0)
            self.assertLess(after["y"], 1080)

        source_edges = {edge["edge_id"]: edge for edge in source["edges"]}
        target_edges = {edge["edge_id"]: edge for edge in target["edges"]}
        self.assertEqual(set(source_edges), set(target_edges))
        for edge_id, before in source_edges.items():
            after = target_edges[edge_id]
            self.assertEqual((before["from_node"], before["to_node"]), (after["from_node"], after["to_node"]))
            self.assertEqual(before["candidate_road_region_ids"], after["candidate_road_region_ids"])
            for point in after["centerline"]["points"]:
                self.assertGreaterEqual(point["x"], 0)
                self.assertLess(point["x"], 1920)
                self.assertGreaterEqual(point["y"], 0)
                self.assertLess(point["y"], 1080)
            _assert_transformed_points(
                self,
                [[p["x"], p["y"]] for p in before["centerline"]["points"]],
                [[p["x"], p["y"]] for p in after["centerline"]["points"]],
                matrix,
            )
            before_barriers = before.get("possible_barriers", [])
            after_barriers = after.get("possible_barriers", [])
            self.assertEqual(len(before_barriers), len(after_barriers))
            for old_barrier, new_barrier in zip(before_barriers, after_barriers):
                old_position = old_barrier.get("position")
                new_position = new_barrier.get("position")
                if old_position and old_position.get("coordinate_system") == "RAW_CAMERA":
                    self.assertIsNotNone(new_position)
                    _assert_transformed_points(
                        self,
                        [[old_position["x"], old_position["y"]]],
                        [[new_position["x"], new_position["y"]]],
                        matrix,
                    )
        for endpoint_id, old_endpoint in source.get("endpoints", {}).items():
            new_endpoint = target["endpoints"][endpoint_id]
            if not isinstance(old_endpoint, dict):
                continue
            old_position = old_endpoint.get("image_position")
            new_position = new_endpoint.get("image_position")
            if old_position and old_position.get("coordinate_system") == "RAW_CAMERA":
                self.assertIsNotNone(new_position)
                _assert_transformed_points(
                    self,
                    [[old_position["x"], old_position["y"]]],
                    [[new_position["x"], new_position["y"]]],
                    matrix,
                )
        self.assertEqual(source["routes"], target["routes"])
        self.assertEqual(source["gate_control_contract"], target["gate_control_contract"])
        self.assertEqual([n["node_id"] for n in target["nodes"]], [f"N{i}" for i in range(1, 11)])
        self.assertEqual([e["edge_id"] for e in target["edges"]], [f"PE{i:02d}" for i in range(1, 10)])

    def test_all_historical_road_vision_artifacts_match_pretest_sha256_manifest(self):
        manifest = _json(HISTORICAL_MANIFEST)
        self.assertEqual(manifest["root"], "reports/debug/road_vision_tests")
        self.assertEqual(len(manifest["files"]), manifest["file_count"])
        self.assertGreater(manifest["file_count"], 0)
        for item in manifest["files"]:
            path = PROJECT_ROOT / Path(item["path"])
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(path.stat().st_size, item["size_bytes"], item["path"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"], item["path"])
