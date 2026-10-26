from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from scripts import roi_calibration


class ROICalibrationGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.draft = roi_calibration.build_initial_draft(
            Path("reference.jpg"),
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            {"camera_index": 0},
            {"runtime_coordinate_system": "RAW_BOARD_CROP"},
            [],
        )

    def test_seed_draft_is_valid_and_never_active(self) -> None:
        validation = roi_calibration.validate_draft(self.draft)
        self.assertTrue(validation["passed"], validation["errors"])
        self.assertTrue(any("overlap at junctions" in warning for warning in validation["warnings"]))
        self.assertEqual(self.draft["status"], "DRAFT_NOT_PRODUCTION_ACTIVE")
        self.assertEqual(self.draft["coordinate_system"], "RAW_CAMERA")
        self.assertEqual(self.draft["routing_edge_mappings"], [])

    def test_building_detection_and_hazard_are_separate_nested_polygons(self) -> None:
        regions = {item["role"]: item for item in self.draft["regions"]}
        self.assertNotEqual(
            regions["building_detection_roi"]["region_id"],
            regions["hazard_polygon"]["region_id"],
        )
        self.assertTrue(
            all(
                roi_calibration.point_in_polygon(point, regions["building_detection_roi"]["points"])
                for point in regions["hazard_polygon"]["points"]
            )
        )

    def test_support_exclusion_candidates_do_not_intersect_road_segments(self) -> None:
        exclusions = [r for r in self.draft["regions"] if r["role"] == "exclusion_mask"]
        segments = [r for r in self.draft["regions"] if r["role"] == "road_segment"]
        self.assertEqual(len(exclusions), 2)
        self.assertEqual(len(segments), 3)
        for exclusion in exclusions:
            for segment in segments:
                self.assertFalse(
                    roi_calibration.polygons_intersect(exclusion["points"], segment["points"]),
                    f"{exclusion['region_id']} intersects {segment['region_id']}",
                )

    def test_preview_coordinate_round_trip_preserves_native_coordinates(self) -> None:
        scale, offset_x, offset_y, _width, _height = roi_calibration.compute_view_transform(
            1920, 1080, 1280, 720
        )
        source = (1234, 678)
        preview = roi_calibration.raw_to_preview(source, scale, offset_x, offset_y)
        restored = roi_calibration.preview_to_raw(preview, scale, offset_x, offset_y)
        self.assertLessEqual(abs(restored[0] - source[0]), 1)
        self.assertLessEqual(abs(restored[1] - source[1]), 1)

    def test_self_intersecting_polygon_is_rejected(self) -> None:
        errors = roi_calibration.validate_polygon(
            [[10, 10], [100, 100], [10, 100], [100, 10]], 1920, 1080
        )
        self.assertTrue(any("self-intersects" in error for error in errors))

    def test_draft_save_reload_and_backup_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "draft.json"
            first = roi_calibration.save_draft(self.draft, path)
            self.assertIsNone(first)
            loaded = roi_calibration.load_draft(path)
            self.assertEqual(loaded["status"], "DRAFT_NOT_PRODUCTION_ACTIVE")

            revised = dict(loaded)
            revised["review_note"] = "second draft save"
            backup = roi_calibration.save_draft(revised, path)
            self.assertEqual(backup, path.with_suffix(".json.bak"))
            self.assertTrue(backup.exists())
            self.assertNotIn("review_note", roi_calibration.load_draft(backup))
            self.assertEqual(roi_calibration.load_draft(path)["review_note"], "second draft save")

    def test_editor_add_move_delete_undo_and_reset_polygon(self) -> None:
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        editor = roi_calibration.ROIEditor(image, roi_calibration.deepcopy(self.draft), Path("draft.json"))
        editor.active_role = "exclusion_mask"
        editor._start_polygon()
        points = [(20, 20), (200, 20), (200, 200)]
        for raw_point in points:
            preview_x, preview_y = roi_calibration.raw_to_preview(
                raw_point, editor.scale, editor.offset_x, editor.offset_y
            )
            editor._mouse(cv2.EVENT_LBUTTONDOWN, round(preview_x), round(preview_y), 0, None)
        editor._close_polygon()

        region = editor.draft["regions"][-1]
        region_id = region["region_id"]
        self.assertEqual(len(region["points"]), 3)
        self.assertTrue(roi_calibration.validate_draft(editor.draft)["passed"])

        preview_x, preview_y = roi_calibration.raw_to_preview(
            (20, 20), editor.scale, editor.offset_x, editor.offset_y
        )
        editor._mouse(cv2.EVENT_LBUTTONDOWN, round(preview_x), round(preview_y), 0, None)
        moved_x, moved_y = roi_calibration.raw_to_preview(
            (35, 35), editor.scale, editor.offset_x, editor.offset_y
        )
        editor._mouse(cv2.EVENT_MOUSEMOVE, round(moved_x), round(moved_y), 0, None)
        editor._mouse(cv2.EVENT_LBUTTONUP, round(moved_x), round(moved_y), 0, None)
        self.assertNotEqual(region["points"][0], [20, 20])

        editor.selected_region_id = region_id
        editor.selected_vertex = 0
        editor._delete_vertex()
        self.assertEqual(len(region["points"]), 2)
        editor._undo()
        region = editor._region(region_id)
        self.assertEqual(len(region["points"]), 3)
        editor._reset_selected()
        self.assertEqual(region["points"], [[20, 20], [200, 20], [200, 200]])

    def test_editor_category_keys_and_comparison_toggle(self) -> None:
        editor = roi_calibration.ROIEditor(
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            roi_calibration.deepcopy(self.draft),
            Path("draft.json"),
        )
        for key, role in roi_calibration.CATEGORY_KEYS.items():
            self.assertTrue(editor._handle_key(key))
            self.assertEqual(editor.active_role, role)
        self.assertTrue(editor.show_existing)
        editor._handle_key(ord("p"))
        self.assertFalse(editor.show_existing)
        editor._handle_key(ord("p"))
        self.assertTrue(editor.show_existing)


if __name__ == "__main__":
    unittest.main()
