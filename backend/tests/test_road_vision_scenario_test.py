"""Unit checks for the TEST_ONLY road-vision scenario adapter."""

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from scripts.road_vision_scenario_test import (
    SCENARIOS,
    CONTROL_BUTTONS,
    LOCATION_KEYS,
    apply_operator_selection,
    capture_missing_requirements,
    hit_test_control_button,
    _frame_stats,
    _quality_status,
    associate_polygon_to_regions,
    class_outcomes,
    normalize_key_code,
    raw_camera_points,
    render_control_panel,
    render_preview,
)


def test_scenario_set_is_complete_and_diagnostic_only() -> None:
    assert [SCENARIOS[str(index)]["id"] for index in range(8)] == [
        f"T{index}" for index in range(8)
    ]
    assert SCENARIOS["1"]["candidate_edge"] == "PE04"
    assert SCENARIOS["2"]["candidate_edge"] == "PE02"
    assert all(
        scenario["candidate_edge"] is None
        for key, scenario in SCENARIOS.items()
        if key in {"0", "5", "6", "7"}
    )


def test_board_crop_polygon_translates_to_raw_camera_coordinates() -> None:
    assert raw_camera_points([[0.5, 1], [14, 30.25]], (408, 66)) == [
        [408.5, 67.0],
        [422.0, 96.25],
    ]


def test_roadblock_truth_maps_to_model_road_obstacle_and_unknown_stays_unscored() -> None:
    outcomes = class_outcomes("ROADBLOCK", {"ROAD_OBSTACLE"})
    assert outcomes["ROAD_OBSTACLE"]["outcome"] == "TP"
    assert outcomes["POTHOLE"]["outcome"] == "TN"
    assert class_outcomes("UNKNOWN", {"POTHOLE"}) == {
        "ROAD_OBSTACLE": None,
        "POTHOLE": None,
    }


def test_no_detection_never_means_road_clear() -> None:
    result = _quality_status("NONE", [], 0.25)
    assert result["status"] == "NO_DETECTION"
    assert "not evidence" in result["note"]
    assert result["class_outcomes"]["ROAD_OBSTACLE"]["outcome"] == "TN"


def test_region_overlap_is_read_only_and_never_assigns_a_graph_edge() -> None:
    valid_mask = np.zeros((40, 40), dtype=np.uint8)
    valid_mask[5:25, 5:25] = 1
    road_mask = SimpleNamespace(
        region=SimpleNamespace(region_id="S1"),
        valid_mask=valid_mask,
    )
    association = associate_polygon_to_regions(
        [[8, 8], [18, 8], [18, 18], [8, 18]],
        (40, 40),
        [road_mask],
        [],
    )
    assert association["association_status"] == "REGION_ONLY"
    assert association["primary_region_id"] == "S1"
    assert association["candidate_graph_edge_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_support_exclusion_is_not_mislabeled_as_valid_road_or_clear() -> None:
    exclusion = SimpleNamespace(
        region_id="support_left",
        board_points=((5, 5), (20, 5), (20, 20), (5, 20)),
    )
    association = associate_polygon_to_regions(
        [[8, 8], [16, 8], [16, 16], [8, 16]],
        (40, 40),
        [],
        [exclusion],
    )
    assert association["association_status"] == "SUPPORT_EXCLUSION_OVERLAP"
    assert association["primary_region_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_outside_polygon_remains_unresolved() -> None:
    association = associate_polygon_to_regions(
        [[25, 25], [35, 25], [35, 35], [25, 35]],
        (40, 40),
        [],
        [],
    )
    assert association["association_status"] == "OUTSIDE_VALID_ROAD_POLYGONS"
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_black_frame_stats_are_explicitly_invalid() -> None:
    stats = _frame_stats(np.zeros((12, 16, 3), dtype=np.uint8))
    assert stats["resolution"] == [16, 12]
    assert stats["all_black"] is True
    assert stats["mean_luma"] == 0
    assert stats["gray_variance"] == 0


def test_operator_panel_and_black_frame_preview_render_without_live_capture() -> None:
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    stats = _frame_stats(frame)
    metadata = SimpleNamespace(timestamp=datetime.now(timezone.utc), width=120, height=80)
    state = {
        "scenario_key": "0",
        "actual_prop_type": "NOT_RECORDED",
        "actual_location": "NOT_RECORDED",
        "visible": None,
        "last_status": "synthetic offline GUI smoke check",
        "roi_overlay": False,
        "grid": False,
        "margins": False,
    }
    preview = render_preview(frame, None, metadata, state, False, None, frame_stats=stats)
    panel = render_control_panel(
        {
            "index": 0,
            "backend_actual": "DSHOW",
            "actual_resolution_first_frame": [120, 80],
            "fourcc_actual_reported": "MJPG",
            "device_reported_fps": -1.0,
        },
        metadata,
        state,
        False,
        None,
        stats,
        0,
        0,
        [],
        [],
        SimpleNamespace(),
    )
    assert preview.shape == frame.shape
    assert panel.shape == (760, 1120, 3)


def test_uppercase_keyboard_shortcuts_are_normalized() -> None:
    assert normalize_key_code(ord("N")) == ord("n")
    assert normalize_key_code(ord("Q")) == ord("q")
    assert normalize_key_code(27) == 27
    assert LOCATION_KEYS[ord("a")] == "PE04"
    assert LOCATION_KEYS[ord("s")] == "PE02"
    assert LOCATION_KEYS[ord("e")] == "OTHER_OR_UNKNOWN"
    assert not set(LOCATION_KEYS).intersection(
        set(map(ord, "01234567rpnuyhgm oq".replace(" ", "")))
    )


def test_t0_none_sets_not_applicable_and_needs_explicit_visibility() -> None:
    state = {
        "scenario_key": "0",
        "scenario_selected": False,
        "actual_prop_type": "NOT_RECORDED",
        "actual_location": "NOT_RECORDED",
        "visible": None,
    }
    apply_operator_selection(state, "scenario", "0")
    apply_operator_selection(state, "truth", "NONE")
    assert state["scenario_selected"] is True
    assert state["actual_location"] == "NOT_APPLICABLE"

    metadata = SimpleNamespace(timestamp=datetime.now(timezone.utc), width=1920, height=1080)
    stats = {"all_black": False, "mean_luma": 125.0, "gray_variance": 4500.0}
    missing = capture_missing_requirements(state, metadata, stats, (1920, 1080), 1.0)
    assert missing == ["confirm visibility: Clearly Visible or Not Clear"]

    apply_operator_selection(state, "visibility", True)
    assert capture_missing_requirements(state, metadata, stats, (1920, 1080), 1.0) == []


def test_unknown_ground_truth_does_not_turn_into_none_and_requires_location() -> None:
    state = {
        "scenario_key": "0",
        "scenario_selected": True,
        "actual_prop_type": "NOT_RECORDED",
        "actual_location": "NOT_RECORDED",
        "visible": True,
    }
    apply_operator_selection(state, "truth", "UNKNOWN")
    assert state["actual_prop_type"] == "UNKNOWN"
    missing = capture_missing_requirements(
        state,
        SimpleNamespace(timestamp=datetime.now(timezone.utc), width=1920, height=1080),
        {"all_black": False},
        (1920, 1080),
        1.0,
    )
    assert "select a physical location" in missing
    assert "select ground truth: NONE, ROADBLOCK, POTHOLE, or UNKNOWN" not in missing


def test_mouse_hit_targets_cover_controls_and_t0_none_location_cannot_be_overridden() -> None:
    assert len(CONTROL_BUTTONS) == 8 + 4 + 9 + 2 + 2
    assert hit_test_control_button(30, 180)["value"] == "0"
    assert hit_test_control_button(30, 300) == {
        "kind": "truth", "value": "NONE", "label": "NONE", "rect": (18, 287, 264, 38)
    }
    assert hit_test_control_button(1000, 700)["kind"] == "exit"
    assert hit_test_control_button(1110, 750) is None

    state = {
        "scenario_key": "0", "scenario_selected": True,
        "actual_prop_type": "NONE", "actual_location": "NOT_APPLICABLE", "visible": True,
    }
    apply_operator_selection(state, "location", "PE04")
    assert state["actual_location"] == "NOT_APPLICABLE"
    assert "NOT_APPLICABLE" in state["last_status"]


def test_capture_readiness_blocks_not_clear_black_stale_and_wrong_size_frames() -> None:
    state = {
        "scenario_key": "0", "scenario_selected": True,
        "actual_prop_type": "NONE", "actual_location": "NOT_APPLICABLE", "visible": False,
    }
    fresh = SimpleNamespace(timestamp=datetime.now(timezone.utc), width=1920, height=1080)
    missing = capture_missing_requirements(
        state, fresh, {"all_black": True}, (1920, 1080), 1.0
    )
    assert "target area is marked Not Clear" in missing
    assert "camera frame is all black" in missing

    state["visible"] = True
    stale = SimpleNamespace(
        timestamp=datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - 1),
        width=640,
        height=480,
    )
    missing = capture_missing_requirements(
        state, stale, {"all_black": False}, (1920, 1080), 1.0
    )
    assert any(item.startswith("wait for a fresh frame") for item in missing)
    assert "camera frame is 640x480, expected 1920x1080" in missing
