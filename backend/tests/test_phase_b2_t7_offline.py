"""Deterministic Phase B2 T7 support-exclusion mask checks.

These tests use only synthetic segmentation polygons and the Phase A draft
coordinates. They never open a camera or call routing, MQTT, dispatch, or
actuator services.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import numpy as np

from app.vision.evidence import RoadVisionEvidenceService
from app.vision.occupancy import calculate_road_occupancy
from app.vision.pipeline import _segmentation_intersects_mask
from app.vision.polygon_roi import load_polygon_roi_config, raw_to_board_point, rasterize_polygon
from app.vision.schemas import (
    BoundingBox,
    CoordinateSystem,
    FrameMetadata,
    FrameSourceType,
    PolygonPoint,
    RoadSegmentationResult,
    SegmentationDetection,
)
from app.vision.spatial import calculate_road_spatial_evidence
from scripts.road_vision_scenario_test import SCENARIOS, associate_polygon_to_regions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_ROOT = Path(os.environ.get("CITYRESPONDER_TEST_DATA_ROOT", PROJECT_ROOT)).expanduser().resolve()
PHASE_A_DRAFT = (
    TEST_DATA_ROOT
    / "reports"
    / "debug"
    / "camera_alignment"
    / "roi_calibration_phase_a_draft.json"
)

# Coordinates are native RAW_CAMERA points selected inside or across the
# unchanged Phase A polygons. They are deterministic synthetic masks, not
# photographs, detections, or claimed physical measurements.
CASES_RAW = {
    "left_support": [(414, 810), (426, 810), (426, 850), (414, 850)],
    "right_support": [(1526, 830), (1538, 830), (1538, 870), (1526, 870)],
    "left_boundary_overlap": [(414, 810), (450, 810), (450, 850), (414, 850)],
    "right_boundary_overlap": [(1500, 830), (1538, 830), (1538, 870), (1500, 870)],
    "valid_road_positive": [(900, 200), (940, 200), (940, 240), (900, 240)],
    "outside_negative": [(500, 500), (540, 500), (540, 540), (500, 540)],
}


def _load_config():
    return load_polygon_roi_config(PHASE_A_DRAFT, expected_resolution=(1920, 1080))


def _board_points(config, case_name: str) -> list[list[float]]:
    return [
        list(raw_to_board_point(point, (config.crop.x, config.crop.y)))
        for point in CASES_RAW[case_name]
    ]


def _synthetic_detection(config, case_name: str) -> SegmentationDetection:
    points = _board_points(config, case_name)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return SegmentationDetection(
        class_name="ROAD_OBSTACLE",
        confidence=1.0,
        bounding_box=BoundingBox(
            x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys)
        ),
        polygon=[PolygonPoint(x=x, y=y) for x, y in points],
        coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
    )


def _evaluate_synthetic_candidate(config, case_name: str):
    detection = _synthetic_detection(config, case_name)
    frame = FrameMetadata(
        frame_id=f"offline-t7-{case_name}",
        timestamp=datetime(2026, 10, 25, tzinfo=timezone.utc),
        source=FrameSourceType.IMAGE_FILE,
        width=config.crop.width,
        height=config.crop.height,
        coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
    )
    masks = config.road_masks((config.crop.height, config.crop.width, 3))
    segmentations = []
    occupancies = []
    spatial = []
    for mask in masks:
        # This is the same valid-mask intersection filter used by the vision
        # pipeline before occupancy and spatial evidence are calculated.
        selected = (
            [detection]
            if _segmentation_intersects_mask(detection, mask.roi, mask.valid_mask)
            else []
        )
        road = RoadSegmentationResult(
            frame=frame,
            road_roi_name=mask.region.label,
            road_roi=mask.roi,
            segmentations=selected,
            processing_timestamp=frame.timestamp,
            road_polygon=mask.region.as_polygon_roi(),
            valid_road_mask=mask.valid_mask,
        )
        segmentations.append(road)
        occupancies.append(calculate_road_occupancy(road))
        spatial.append(calculate_road_spatial_evidence(road))

    evidence = RoadVisionEvidenceService().combine(segmentations, occupancies, spatial)
    associations = associate_polygon_to_regions(
        _board_points(config, case_name),
        (config.crop.height, config.crop.width),
        masks,
        list(config.exclusions),
    )
    return masks, segmentations, occupancies, evidence, associations


def test_draft_support_masks_are_removed_from_every_valid_road_mask():
    config = _load_config()
    masks = config.road_masks((config.crop.height, config.crop.width, 3))

    for exclusion in config.exclusions:
        exclusion_mask = rasterize_polygon(
            exclusion.board_points, config.crop.width, config.crop.height
        )
        for road in masks:
            assert not np.any((exclusion_mask != 0) & (road.valid_mask != 0))


def test_left_and_right_support_only_candidates_make_no_road_evidence():
    config = _load_config()

    for case_name, expected_exclusion in (
        ("left_support", "exclude_left_support_candidate"),
        ("right_support", "exclude_right_support_candidate"),
    ):
        masks, segmentations, occupancies, evidence, association = (
            _evaluate_synthetic_candidate(config, case_name)
        )
        assert association["association_status"] == "SUPPORT_EXCLUSION_OVERLAP"
        assert association["primary_region_id"] is None
        assert association["region_overlaps"] == []
        assert association["support_exclusion_overlaps"] == [
            {
                "region_id": expected_exclusion,
                "intersection_pixels": association["mask_pixel_count"],
            }
        ]
        assert all(road.segmentations == [] for road in segmentations)
        assert all(result.occupied_pixels == 0 for result in occupancies)
        assert all(result.contributing_classes == [] for result in evidence)
        assert all(result.contributing_detections == [] for result in evidence)
        assert all(result.obstacle_count == 0 for result in evidence)
        assert all(
            result.roi_pixels == int(np.count_nonzero(mask.valid_mask))
            for result, mask in zip(occupancies, masks)
        )
        assert association["candidate_graph_edge_id"] is None
        assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_partial_support_boundary_overlap_counts_only_valid_road_pixels():
    config = _load_config()
    masks, segmentations, occupancies, evidence, association = (
        _evaluate_synthetic_candidate(config, "left_boundary_overlap")
    )

    assert association["association_status"] == "REGION_ONLY"
    assert association["primary_region_id"] == "road_lower_horizontal_candidate"
    assert association["support_exclusion_overlaps"][0]["region_id"] == (
        "exclude_left_support_candidate"
    )
    assert association["support_exclusion_overlaps"][0]["intersection_pixels"] > 0
    region_overlap = association["region_overlaps"]
    assert [item["region_id"] for item in region_overlap] == [
        "road_lower_horizontal_candidate"
    ]
    assert region_overlap[0]["junction_owner_rule_applied"] is True

    evidence_by_region = {result.road_roi_name: result for result in evidence}
    occupied = sum(result.occupied_pixels for result in occupancies)
    assert occupied == region_overlap[0]["intersection_pixels"]
    assert 0 < occupied < association["mask_pixel_count"]
    assert evidence_by_region["S3"].occupied_pixels == occupied
    assert evidence_by_region["S3"].obstacle_count == 1
    assert evidence_by_region["S1"].occupied_pixels == 0
    assert evidence_by_region["S2"].occupied_pixels == 0
    assert all(
        result.roi_pixels == int(np.count_nonzero(mask.valid_mask))
        for result, mask in zip(occupancies, masks)
    )
    assert association["candidate_graph_edge_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_right_boundary_partial_overlap_uses_existing_valid_road_precedence():
    config = _load_config()
    _masks, _segmentations, occupancies, evidence, association = (
        _evaluate_synthetic_candidate(config, "right_boundary_overlap")
    )

    assert association["association_status"] == "REGION_ONLY"
    assert association["primary_region_id"] == "road_lower_horizontal_candidate"
    assert association["support_exclusion_overlaps"][0]["region_id"] == (
        "exclude_right_support_candidate"
    )
    assert association["support_exclusion_overlaps"][0]["intersection_pixels"] > 0
    assert sum(result.occupied_pixels for result in occupancies) == (
        association["region_overlaps"][0]["intersection_pixels"]
    )
    assert sum(result.obstacle_count for result in evidence) == 1
    assert association["candidate_graph_edge_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_valid_road_positive_control_produces_road_evidence_but_no_edge_mapping():
    config = _load_config()
    _masks, segmentations, occupancies, evidence, association = (
        _evaluate_synthetic_candidate(config, "valid_road_positive")
    )

    assert association["association_status"] == "REGION_ONLY"
    assert association["primary_region_id"] == "road_upper_horizontal_candidate"
    assert association["support_exclusion_overlaps"] == []
    assert sum(result.occupied_pixels for result in occupancies) > 0
    assert sum(result.obstacle_count for result in evidence) == 1
    assert sum(bool(road.segmentations) for road in segmentations) == 1
    assert association["candidate_graph_edge_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_outside_negative_control_stays_unresolved_without_road_evidence():
    config = _load_config()
    _masks, segmentations, occupancies, evidence, association = (
        _evaluate_synthetic_candidate(config, "outside_negative")
    )

    assert association["association_status"] == "OUTSIDE_VALID_ROAD_POLYGONS"
    assert association["primary_region_id"] is None
    assert association["region_overlaps"] == []
    assert association["support_exclusion_overlaps"] == []
    assert all(road.segmentations == [] for road in segmentations)
    assert all(result.occupied_pixels == 0 for result in occupancies)
    assert all(result.obstacle_count == 0 for result in evidence)
    assert association["candidate_graph_edge_id"] is None
    assert association["edge_mapping_status"] == "EDGE_UNRESOLVED"


def test_t7_is_marked_fixture_constrained_and_disabled_for_physical_capture():
    from scripts.road_vision_scenario_test import capture_missing_requirements

    assert SCENARIOS["7"]["physical_validation_status"] == (
        "NOT_EXECUTED_PHYSICAL — FIXTURE_CONSTRAINT"
    )
    assert "offline" in SCENARIOS["7"]["name"].lower()
    missing = capture_missing_requirements(
        {
            "scenario_key": "7",
            "scenario_selected": True,
            "actual_prop_type": "ROADBLOCK",
            "actual_location": "SUPPORT_EXCLUSION",
            "visible": True,
        },
        None,
        None,
        (1920, 1080),
        1.0,
    )
    assert any(
        "NOT_EXECUTED_PHYSICAL — FIXTURE_CONSTRAINT" in item for item in missing
    )


def test_phase_a_draft_keeps_all_road_edge_mappings_unresolved():
    draft = json.loads(PHASE_A_DRAFT.read_text(encoding="utf-8"))
    assert draft["routing_edge_mappings"] == []
    assert draft["phase_a_integration"]["routing_edge_mappings"] == []
    assert all(
        region.get("routing_edge_id") is None
        for region in draft["regions"]
        if region.get("role") == "road_segment"
    )
