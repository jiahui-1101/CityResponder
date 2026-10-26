"""Edit and preview RAW_CAMERA ROI polygons without changing production settings.

The editor reads the current Settings-backed rectangular ROIs for comparison,
but it writes only an explicitly non-active draft. Production currently stores
ROI rectangles in RAW_BOARD_CROP coordinates and has no polygon mask contract.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import cv2
import numpy as np


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_REFERENCE_DIR = PROJECT_ROOT / "reports" / "debug" / "camera_alignment"
DEFAULT_DRAFT_PATH = DEFAULT_REFERENCE_DIR / "roi_calibration_draft.json"
DEFAULT_ANNOTATED_PATH = DEFAULT_REFERENCE_DIR / "roi_calibration_draft_annotated.jpg"
WINDOW_NAME = "CityResponder - ROI Calibration Draft"
PREVIEW_SIZE = (1280, 720)

# OpenCV colors are BGR.
COLORS: dict[str, tuple[int, int, int]] = {
    "processing_crop": (255, 220, 0),
    "building_detection_roi": (0, 255, 255),
    "hazard_polygon": (0, 0, 255),
    "road_segmentation_roi": (0, 165, 255),
    "road_segment": (0, 220, 60),
    "exclusion_mask": (255, 0, 255),
    "legacy": (190, 190, 190),
    "selected": (255, 255, 255),
    "ir_a": (0, 255, 255),
    "ir_b": (255, 0, 255),
}

CATEGORY_KEYS = {
    ord("1"): "building_detection_roi",
    ord("2"): "hazard_polygon",
    ord("3"): "road_segmentation_roi",
    ord("4"): "road_segment",
    ord("5"): "ir_association",
    ord("6"): "exclusion_mask",
    ord("7"): "processing_crop",
}

CATEGORY_LABELS = {
    "building_detection_roi": "Building A detection ROI",
    "hazard_polygon": "Building A hazard polygon",
    "road_segmentation_roi": "Road segmentation ROI",
    "road_segment": "Individual road segment",
    "ir_association": "IR road association",
    "exclusion_mask": "Exclusion mask",
    "processing_crop": "Candidate processing crop",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        type=Path,
        help="Full-resolution reference JPEG; defaults to the newest *_raw.jpg",
    )
    parser.add_argument(
        "--draft",
        type=Path,
        default=DEFAULT_DRAFT_PATH,
        help="Draft JSON path; never writes production settings",
    )
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="Create a fresh draft and annotated preview, then exit",
    )
    parser.add_argument(
        "--force-reinitialize",
        action="store_true",
        help="Replace an existing draft after preserving a .bak copy",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the selected draft and print a JSON report",
    )
    parser.add_argument(
        "--render-to",
        type=Path,
        help="Write a full-resolution annotated preview and exit",
    )
    return parser.parse_args()


def find_latest_raw_image(directory: Path = DEFAULT_REFERENCE_DIR) -> Path:
    images = sorted(directory.glob("*_raw.jpg"), key=lambda path: path.stat().st_mtime)
    if not images:
        raise FileNotFoundError(f"No raw camera snapshots found in {directory}")
    return images[-1]


def load_reference(image_path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to load reference image: {image_path}")
    metadata_path = image_path.with_name(image_path.name.replace("_raw.jpg", "_metadata.json"))
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read reference metadata: {metadata_path}") from exc
    return image, metadata


def load_canonical_roi_configuration() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read Settings-backed production values without changing them."""

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import get_settings
    from app.vision.config import get_vision_config
    from app.vision.roi import get_configured_rois

    settings = get_settings()
    config = get_vision_config()
    rois = get_configured_rois(config)
    board = rois["board"][0] if rois["board"] else None
    offset_x = board.x if board is not None else 0
    offset_y = board.y if board is not None else 0

    source_configuration = {
        "source_of_truth": "backend/app/core/config.py Settings plus environment/backend/.env",
        "runtime_coordinate_system": "RAW_BOARD_CROP",
        "camera": {
            "source": settings.vision_source,
            "index": settings.vision_camera_index,
            "requested_resolution": [settings.vision_frame_width, settings.vision_frame_height],
            "require_exact_frame_size": settings.vision_require_exact_frame_size,
        },
        "board_crop": [item.model_dump(mode="json") for item in rois["board"]],
        "building_roi": [item.model_dump(mode="json") for item in rois["building_a"]],
        "road_rois": [item.model_dump(mode="json") for item in rois["road"]],
        "hazard_rois": [item.model_dump(mode="json") for item in rois["hazard_zone"]],
        "road_ir_mapping_json": config.road_ir_mapping,
        "pixel_to_cm_scale": config.pixel_to_cm_scale,
        "production_capture_contract": {
            "backend": "cv2.VideoCapture(source) / CAP_ANY",
            "fourcc_request": None,
        },
    }

    legacy_regions: list[dict[str, Any]] = []
    groups = (
        ("board", "Existing board crop"),
        ("building_a", "Existing Building A rectangle"),
        ("road", "Existing road rectangle"),
        ("hazard_zone", "Existing hazard rectangle"),
    )
    for group, label in groups:
        for index, roi in enumerate(rois[group], start=1):
            points = rect_to_points(
                roi.x + offset_x,
                roi.y + offset_y,
                roi.width,
                roi.height,
            )
            legacy_regions.append(
                {
                    "region_id": f"existing_{group}_{index}",
                    "name": label if index == 1 else f"{label} {index}",
                    "role": "legacy",
                    "coordinate_system": "RAW_CAMERA",
                    "points": points,
                }
            )
    return source_configuration, legacy_regions


def rect_to_points(x: int, y: int, width: int, height: int) -> list[list[int]]:
    return [
        [x, y],
        [x + width, y],
        [x + width, y + height],
        [x, y + height],
    ]


def _region(
    region_id: str,
    name: str,
    role: str,
    points: list[list[int]],
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "name": name,
        "role": role,
        "coordinate_system": "RAW_CAMERA",
        "points": deepcopy(points),
        "initial_points": deepcopy(points),
        "editable": True,
        "status": "DRAFT_NEEDS_REVIEW",
        **attributes,
    }


def build_initial_draft(
    image_path: Path,
    image: np.ndarray,
    image_metadata: dict[str, Any],
    source_configuration: dict[str, Any],
    legacy_regions: list[dict[str, Any]],
) -> dict[str, Any]:
    height, width = image.shape[:2]
    regions = [
        _region(
            "processing_crop_candidate",
            "Candidate processing crop",
            "processing_crop",
            rect_to_points(430, 90, 1088, 800),
            label="CANDIDATE CROP",
            label_anchor=[438, 168],
            geometry_basis="traced from the visible road-system bounds in the reference image",
        ),
        _region(
            "building_a_detection_candidate",
            "Building A detection ROI candidate",
            "building_detection_roi",
            [[902, 438], [1208, 438], [1208, 690], [902, 690]],
            label="BUILDING A ROI",
            label_anchor=[906, 430],
            geometry_basis="traced around the visible outer Building A tray boundary",
        ),
        _region(
            "building_a_hazard_candidate",
            "Building A hazard polygon candidate",
            "hazard_polygon",
            [[920, 478], [1188, 478], [1190, 672], [918, 672]],
            label="HAZARD AREA",
            label_anchor=[924, 470],
            geometry_basis="traced inside the visible tray floor; requires operator review",
        ),
        _region(
            "road_network_candidate",
            "Visible road-network segmentation ROI candidate",
            "road_segmentation_roi",
            [
                [720, 90],
                [832, 90],
                [832, 184],
                [1518, 184],
                [1518, 295],
                [832, 295],
                [832, 778],
                [1518, 778],
                [1518, 890],
                [432, 890],
                [432, 778],
                [720, 778],
            ],
            label="ROAD ROI",
            label_anchor=[840, 310],
            geometry_basis="traced from visible road surfaces; not mapped to routing edges",
        ),
        _region(
            "road_upper_horizontal_candidate",
            "Upper horizontal road segment candidate",
            "road_segment",
            [[720, 184], [1518, 184], [1518, 295], [720, 295]],
            label="S1 — UNMAPPED",
            label_anchor=[1070, 218],
            routing_edge_id=None,
            ir_sensor=None,
        ),
        _region(
            "road_main_vertical_candidate",
            "Main vertical road segment candidate",
            "road_segment",
            [[720, 90], [832, 90], [832, 778], [720, 778]],
            label="S2 — UNMAPPED",
            label_anchor=[742, 520],
            routing_edge_id=None,
            ir_sensor=None,
        ),
        _region(
            "road_lower_horizontal_candidate",
            "Lower horizontal road segment candidate",
            "road_segment",
            [[432, 778], [1518, 778], [1518, 890], [432, 890]],
            label="S3 — UNMAPPED",
            label_anchor=[1000, 850],
            routing_edge_id=None,
            ir_sensor=None,
        ),
        _region(
            "exclude_left_support_candidate",
            "Left support / off-board exclusion candidate",
            "exclusion_mask",
            [[0, 792], [430, 776], [430, 888], [0, 930]],
            label="LEFT SUPPORT EXCLUDED",
            label_anchor=[36, 840],
            geometry_basis="traced from visible left support beam; kept outside road polygons",
        ),
        _region(
            "exclude_right_support_candidate",
            "Right support / off-board exclusion candidate",
            "exclusion_mask",
            [[1520, 776], [1919, 805], [1919, 964], [1520, 890]],
            label="RIGHT SUPPORT EXCLUDED",
            label_anchor=[1560, 840],
            geometry_basis="traced from visible right support beam; kept outside road polygons",
        ),
    ]
    # Store actual frame dimensions in the draft, not dimensions inferred from a preview.
    return {
        "schema_version": 1,
        "status": "DRAFT_NOT_PRODUCTION_ACTIVE",
        "coordinate_system": "RAW_CAMERA",
        "image_size": {"width": width, "height": height},
        "reference_image": str(image_path.resolve()),
        "reference_metadata": image_metadata,
        "source_configuration_backup": source_configuration,
        "legacy_overlay_raw_camera": legacy_regions,
        "regions": regions,
        "routing_edge_mappings": [],
        "ir_associations": {
            "IR_A": {"road_region_id": None, "status": "NEEDS PHYSICAL CONFIRMATION"},
            "IR_B": {"road_region_id": None, "status": "NEEDS PHYSICAL CONFIRMATION"},
        },
        "limitations": [
            "The two lower buildings are partly outside the camera frame and are not represented as fully visible.",
            "Road candidates are not mapped to graph edges because no production topology is configured in this repository.",
            "IR_A and IR_B road associations require physical confirmation.",
            "Polygon masks are draft-only; the production pipeline currently consumes rectangular RAW_BOARD_CROP ROIs.",
        ],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def polygon_area(points: list[list[float]] | list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            float(points[index][0]) * float(points[(index + 1) % len(points)][1])
            - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
            for index in range(len(points))
        )
        / 2.0
    )


def _orientation(a: Any, b: Any, c: Any) -> float:
    return (float(b[0]) - float(a[0])) * (float(c[1]) - float(a[1])) - (
        float(b[1]) - float(a[1])
    ) * (float(c[0]) - float(a[0]))


def _on_segment(a: Any, b: Any, p: Any, tolerance: float = 1e-7) -> bool:
    if abs(_orientation(a, b, p)) > tolerance:
        return False
    return (
        min(float(a[0]), float(b[0])) - tolerance
        <= float(p[0])
        <= max(float(a[0]), float(b[0])) + tolerance
        and min(float(a[1]), float(b[1])) - tolerance
        <= float(p[1])
        <= max(float(a[1]), float(b[1])) + tolerance
    )


def _segments_intersect(a: Any, b: Any, c: Any, d: Any) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return (
        _on_segment(a, b, c)
        or _on_segment(a, b, d)
        or _on_segment(c, d, a)
        or _on_segment(c, d, b)
    )


def polygons_intersect(first: list[list[float]], second: list[list[float]]) -> bool:
    if len(first) < 3 or len(second) < 3:
        return False
    for i, a in enumerate(first):
        b = first[(i + 1) % len(first)]
        for j, c in enumerate(second):
            d = second[(j + 1) % len(second)]
            if _segments_intersect(a, b, c, d):
                return True
    return point_in_polygon(first[0], second) or point_in_polygon(second[0], first)


def point_in_polygon(point: Any, polygon: list[list[float]]) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if _on_segment(a, b, (x, y)):
            return True
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        if (ay > y) != (by > y):
            crossing_x = (bx - ax) * (y - ay) / (by - ay) + ax
            if x < crossing_x:
                inside = not inside
    return inside


def validate_polygon(
    points: list[list[float]], image_width: int, image_height: int
) -> list[str]:
    errors: list[str] = []
    if len(points) < 3:
        return ["polygon requires at least 3 vertices"]
    normalized: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            errors.append(f"vertex {index} must be an x/y pair")
            continue
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            errors.append(f"vertex {index} is not numeric")
            continue
        if not math.isfinite(x) or not math.isfinite(y):
            errors.append(f"vertex {index} is not finite")
            continue
        if x < 0 or y < 0 or x > image_width - 1 or y > image_height - 1:
            errors.append(f"vertex {index} is outside {image_width}x{image_height} RAW_CAMERA bounds")
        normalized.append((x, y))
    if len(normalized) != len(points):
        return errors
    if len(set(normalized)) < 3:
        errors.append("polygon requires at least 3 distinct vertices")
    if polygon_area(normalized) < 4.0:
        errors.append("polygon area is too small")
    count = len(normalized)
    for i in range(count):
        a, b = normalized[i], normalized[(i + 1) % count]
        if a == b:
            errors.append(f"edge {i} has zero length")
        for j in range(i + 1, count):
            # Adjacent edges (including first/last) share an expected endpoint.
            if j == i or j == (i + 1) % count or (j + 1) % count == i:
                continue
            c, d = normalized[j], normalized[(j + 1) % count]
            if _segments_intersect(a, b, c, d):
                errors.append(f"polygon self-intersects at edges {i} and {j}")
    return sorted(set(errors))


def validate_draft(draft: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if draft.get("schema_version") != 1:
        errors.append("unsupported draft schema_version")
    if draft.get("status") != "DRAFT_NOT_PRODUCTION_ACTIVE":
        errors.append("draft status must remain DRAFT_NOT_PRODUCTION_ACTIVE")
    if draft.get("coordinate_system") != "RAW_CAMERA":
        errors.append("draft coordinates must be RAW_CAMERA")
    size = draft.get("image_size", {})
    try:
        width, height = int(size["width"]), int(size["height"])
    except (KeyError, TypeError, ValueError):
        return {"passed": False, "errors": ["draft image_size is missing or invalid"], "warnings": []}
    if width <= 0 or height <= 0:
        return {"passed": False, "errors": ["draft image_size must be positive"], "warnings": []}

    regions = draft.get("regions")
    if not isinstance(regions, list):
        return {"passed": False, "errors": errors + ["regions must be a list"], "warnings": warnings}
    by_id: dict[str, dict[str, Any]] = {}
    by_role: dict[str, list[dict[str, Any]]] = {}
    for region in regions:
        if not isinstance(region, dict):
            errors.append("each region must be an object")
            continue
        region_id = str(region.get("region_id", ""))
        if not region_id:
            errors.append("region_id is required")
            continue
        if region_id in by_id:
            errors.append(f"duplicate region_id: {region_id}")
        by_id[region_id] = region
        role = str(region.get("role", ""))
        by_role.setdefault(role, []).append(region)
        if region.get("coordinate_system") != "RAW_CAMERA":
            errors.append(f"{region_id} is not in RAW_CAMERA coordinates")
        polygon_errors = validate_polygon(region.get("points", []), width, height)
        errors.extend(f"{region_id}: {message}" for message in polygon_errors)

    def exactly_one(role: str, label: str) -> dict[str, Any] | None:
        role_regions = by_role.get(role, [])
        if len(role_regions) != 1:
            errors.append(f"expected exactly one {label}; found {len(role_regions)}")
            return None
        return role_regions[0]

    crop = exactly_one("processing_crop", "processing crop candidate")
    building = exactly_one("building_detection_roi", "Building A detection ROI")
    hazard = exactly_one("hazard_polygon", "Building A hazard polygon")
    road_domain = exactly_one("road_segmentation_roi", "road segmentation ROI")
    road_segments = by_role.get("road_segment", [])
    exclusions = by_role.get("exclusion_mask", [])
    if len(road_segments) < 3:
        errors.append("at least three visible road segment candidates are required")
    if len(exclusions) < 2:
        errors.append("left and right support exclusion candidates are required")

    if crop:
        crop_points = crop.get("points", [])
        if len(crop_points) != 4:
            errors.append("processing crop candidate must be a four-corner rectangle")
        elif not (
            crop_points[0][1] == crop_points[1][1]
            and crop_points[1][0] == crop_points[2][0]
            and crop_points[2][1] == crop_points[3][1]
            and crop_points[3][0] == crop_points[0][0]
        ):
            errors.append("processing crop candidate must remain axis-aligned")
        if road_domain:
            for point in road_domain.get("points", []):
                if not point_in_polygon(point, crop_points):
                    errors.append("road segmentation ROI extends outside processing crop candidate")
                    break
        for region in [building, hazard, *road_segments]:
            if region and any(
                not point_in_polygon(point, crop_points)
                for point in region.get("points", [])
            ):
                errors.append(f"{region.get('region_id')} extends outside processing crop candidate")

    if building and hazard:
        building_points = building.get("points", [])
        if any(not point_in_polygon(point, building_points) for point in hazard.get("points", [])):
            errors.append("hazard polygon must be fully contained by the Building A detection ROI")
    if road_domain:
        domain_points = road_domain.get("points", [])
        for segment in road_segments:
            if any(not point_in_polygon(point, domain_points) for point in segment.get("points", [])):
                errors.append(f"{segment.get('region_id')} lies outside road segmentation ROI")
    for exclusion in exclusions:
        for segment in road_segments:
            if polygons_intersect(exclusion.get("points", []), segment.get("points", [])):
                errors.append(
                    f"{exclusion.get('region_id')} intersects {segment.get('region_id')}; check that valid road is not excluded"
                )
    for index, first_segment in enumerate(road_segments):
        for second_segment in road_segments[index + 1 :]:
            if polygons_intersect(first_segment.get("points", []), second_segment.get("points", [])):
                warnings.append(
                    "road segment candidates overlap at junctions; partition against measured graph edges before mapping"
                )

    edges = draft.get("routing_edge_mappings", [])
    if edges:
        errors.append("routing edge mappings cannot be validated without a repository production topology")
    for sensor, association in draft.get("ir_associations", {}).items():
        if association.get("road_region_id") is None:
            warnings.append(f"{sensor} mapping is NEEDS PHYSICAL CONFIRMATION")
        elif association.get("road_region_id") not in by_id:
            errors.append(f"{sensor} association references an unknown road region")
        else:
            warnings.append(f"{sensor} association remains draft pending physical confirmation")
    if len(regions) > 0:
        warnings.extend(
            [
                "Draft polygons are not consumed by the production pipeline.",
                "Lower two buildings remain partly outside the image and are not fully detectable.",
            ]
        )
    return {"passed": not errors, "errors": sorted(set(errors)), "warnings": sorted(set(warnings))}


def compute_view_transform(
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> tuple[float, float, float, int, int]:
    scale = min(target_width / source_width, target_height / source_height)
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))
    offset_x = (target_width - width) // 2
    offset_y = (target_height - height) // 2
    return scale, float(offset_x), float(offset_y), width, height


def raw_to_preview(
    point: tuple[float, float],
    scale: float,
    offset_x: float,
    offset_y: float,
) -> tuple[float, float]:
    return point[0] * scale + offset_x, point[1] * scale + offset_y


def preview_to_raw(
    point: tuple[float, float],
    scale: float,
    offset_x: float,
    offset_y: float,
) -> tuple[int, int]:
    return round((point[0] - offset_x) / scale), round((point[1] - offset_y) / scale)


def draw_dashed_polygon(
    image: np.ndarray,
    points: list[list[float]],
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    for index, first in enumerate(points):
        second = points[(index + 1) % len(points)]
        x1, y1 = int(round(first[0])), int(round(first[1]))
        x2, y2 = int(round(second[0])), int(round(second[1]))
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        dash = 14
        for start in range(0, int(length), dash * 2):
            end = min(length, start + dash)
            start_ratio, end_ratio = start / length, end / length
            cv2.line(
                image,
                (round(x1 + (x2 - x1) * start_ratio), round(y1 + (y2 - y1) * start_ratio)),
                (round(x1 + (x2 - x1) * end_ratio), round(y1 + (y2 - y1) * end_ratio)),
                color,
                thickness,
                cv2.LINE_AA,
            )


def render_draft(
    image: np.ndarray,
    draft: dict[str, Any],
    *,
    show_existing: bool = True,
    status: str = "",
    selected_region_id: str | None = None,
    selected_vertex: int | None = None,
    drawing_points: list[list[int]] | None = None,
    cursor_raw: tuple[int, int] | None = None,
) -> np.ndarray:
    output = image.copy()
    regions = draft.get("regions", [])
    overlay = output.copy()
    for region in regions:
        points = region.get("points", [])
        if len(points) < 3:
            continue
        role = region.get("role", "")
        if role in {"exclusion_mask", "road_segmentation_roi"}:
            cv2.fillPoly(
                overlay,
                [np.asarray(points, dtype=np.int32)],
                COLORS.get(role, COLORS["legacy"]),
            )
    output = cv2.addWeighted(overlay, 0.12, output, 0.88, 0)

    if show_existing:
        for region in draft.get("legacy_overlay_raw_camera", []):
            points = region.get("points", [])
            if len(points) >= 3:
                draw_dashed_polygon(output, points, COLORS["legacy"], 2)
                cv2.putText(
                    output,
                    region.get("name", "existing ROI"),
                    (int(points[0][0]), max(150, int(points[0][1]) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    COLORS["legacy"],
                    2,
                    cv2.LINE_AA,
                )

    for region in regions:
        points = region.get("points", [])
        if len(points) < 2:
            continue
        region_id = region.get("region_id")
        role = region.get("role", "legacy")
        color = COLORS.get(role, COLORS["legacy"])
        if role == "road_segment" and region.get("ir_sensor") in {"IR_A", "IR_B"}:
            color = COLORS["ir_a"] if region["ir_sensor"] == "IR_A" else COLORS["ir_b"]
        if len(points) >= 3:
            cv2.polylines(
                output,
                [np.asarray(points, dtype=np.int32)],
                True,
                color,
                4 if region_id == selected_region_id else 3,
                cv2.LINE_AA,
            )
            center = np.mean(np.asarray(points, dtype=np.float32), axis=0)
            label_anchor = region.get("label_anchor", center)
            label_x = max(6, min(output.shape[1] - 360, int(label_anchor[0])))
            label_y = max(128, min(output.shape[0] - 12, int(label_anchor[1])))
            label = str(region.get("label") or region.get("name", region_id))[:36]
            cv2.putText(
                output,
                label,
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 0, 0),
                5,
                cv2.LINE_AA,
            )
            cv2.putText(
                output,
                label,
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )
        else:
            cv2.polylines(
                output,
                [np.asarray(points, dtype=np.int32)],
                False,
                color,
                3,
                cv2.LINE_AA,
            )
        for index, point in enumerate(points):
            center = (int(round(point[0])), int(round(point[1])))
            radius = 9 if region_id == selected_region_id and index == selected_vertex else 6
            cv2.circle(output, center, radius, COLORS["selected"] if radius == 9 else color, -1, cv2.LINE_AA)
            cv2.circle(output, center, radius + 2, (0, 0, 0), 1, cv2.LINE_AA)

    if drawing_points:
        active_color = COLORS.get("road_segment", (0, 255, 0))
        if drawing_points:
            cv2.polylines(
                output,
                [np.asarray(drawing_points, dtype=np.int32)],
                False,
                active_color,
                2,
                cv2.LINE_AA,
            )
            for point in drawing_points:
                cv2.circle(output, tuple(point), 7, active_color, -1, cv2.LINE_AA)
    if cursor_raw is not None:
        cv2.drawMarker(
            output,
            cursor_raw,
            (255, 255, 255),
            cv2.MARKER_CROSS,
            18,
            2,
            cv2.LINE_AA,
        )

    panel = output.copy()
    cv2.rectangle(panel, (0, 0), (output.shape[1] - 1, 112), (12, 12, 12), -1)
    output = cv2.addWeighted(panel, 0.90, output, 0.10, 0)
    lines = [
        f"ROI DRAFT — NOT PRODUCTION ACTIVE — RAW_CAMERA {draft['image_size']['width']}x{draft['image_size']['height']}",
        "1-7 choose type | N draw | Enter/right-click close | Drag move | Shift+Click edge to add | X delete | U undo | R reset",
        "S save | L reload | P toggle old ROIs | Q/Esc exit | Cyan crop / yellow building / red hazard / orange road / green segments / magenta support mask",
    ]
    context: list[str] = []
    if selected_region_id:
        region = next((item for item in regions if item.get("region_id") == selected_region_id), None)
        if region:
            context.append(f"Selected: {region.get('name')}")
    if cursor_raw is not None:
        context.append(f"RAW_CAMERA x={cursor_raw[0]} y={cursor_raw[1]}")
    if status:
        context.append(status)
    if context:
        lines.append(" | ".join(context))
    for index, line in enumerate(lines):
        cv2.putText(
            output,
            line[:210],
            (14, 24 + 25 * index),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (0, 255, 190) if index == 0 else (245, 245, 245),
            2 if index == 0 else 1,
            cv2.LINE_AA,
        )
    return output


def fit_image_for_display(image: np.ndarray, target_size: tuple[int, int]) -> tuple[np.ndarray, tuple[float, float, float, int, int]]:
    target_width, target_height = target_size
    source_height, source_width = image.shape[:2]
    transform = compute_view_transform(source_width, source_height, target_width, target_height)
    scale, offset_x, offset_y, width, height = transform
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    canvas[int(offset_y) : int(offset_y) + height, int(offset_x) : int(offset_x) + width] = resized
    return canvas, transform


def save_draft(draft: dict[str, Any], path: Path) -> Path | None:
    validation = validate_draft(draft)
    if not validation["passed"]:
        raise ValueError("Draft validation failed: " + "; ".join(validation["errors"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = path.with_suffix(path.suffix + ".bak") if path.exists() else None
    if backup_path is not None:
        shutil.copy2(path, backup_path)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)
    return backup_path


def load_draft(path: Path) -> dict[str, Any]:
    draft = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise ValueError("Draft root must be a JSON object")
    validation = validate_draft(draft)
    if not validation["passed"]:
        raise ValueError("Saved draft is invalid: " + "; ".join(validation["errors"]))
    return draft


class ROIEditor:
    def __init__(
        self,
        image: np.ndarray,
        draft: dict[str, Any],
        draft_path: Path,
    ) -> None:
        self.image = image
        self.draft = draft
        self.draft_path = draft_path
        self.active_role = "building_detection_roi"
        self.selected_region_id: str | None = None
        self.selected_vertex: int | None = None
        self.drawing: dict[str, Any] | None = None
        self.drag_vertex: tuple[str, int] | None = None
        self.show_existing = True
        self.cursor_raw: tuple[int, int] | None = None
        self.status = "Ready. Existing outlines are dashed gray; draft geometry is editable."
        self.undo_stack: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        height, width = image.shape[:2]
        self.scale, self.offset_x, self.offset_y, self.display_width, self.display_height = compute_view_transform(
            width, height, PREVIEW_SIZE[0], PREVIEW_SIZE[1]
        )

    def _snapshot_undo(self) -> None:
        self.undo_stack.append((deepcopy(self.draft), deepcopy(self.drawing)))
        if len(self.undo_stack) > 64:
            self.undo_stack.pop(0)

    def _regions_for_active_role(self) -> list[dict[str, Any]]:
        return [region for region in self.draft["regions"] if region.get("role") == self.active_role]

    def _region(self, region_id: str | None) -> dict[str, Any] | None:
        if region_id is None:
            return None
        return next(
            (region for region in self.draft["regions"] if region.get("region_id") == region_id),
            None,
        )

    def _display_to_raw(self, x: int, y: int) -> tuple[int, int] | None:
        raw_x, raw_y = preview_to_raw((x, y), self.scale, self.offset_x, self.offset_y)
        if raw_x < 0 or raw_y < 0 or raw_x >= self.image.shape[1] or raw_y >= self.image.shape[0]:
            return None
        return raw_x, raw_y

    def _nearest_vertex(self, point: tuple[int, int], region: dict[str, Any]) -> tuple[int, float] | None:
        best: tuple[int, float] | None = None
        for index, vertex in enumerate(region.get("points", [])):
            distance = math.hypot(point[0] - vertex[0], point[1] - vertex[1])
            if best is None or distance < best[1]:
                best = (index, distance)
        threshold_raw = max(12, round(20 / self.scale))
        return best if best is not None and best[1] <= threshold_raw else None

    def _nearest_edge(self, point: tuple[int, int], region: dict[str, Any]) -> int | None:
        points = region.get("points", [])
        if len(points) < 2:
            return None
        closest_index: int | None = None
        closest_distance = float("inf")
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            dx, dy = end[0] - start[0], end[1] - start[1]
            denominator = dx * dx + dy * dy
            ratio = 0.0 if denominator == 0 else max(
                0.0,
                min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator),
            )
            projected = (start[0] + ratio * dx, start[1] + ratio * dy)
            distance = math.hypot(point[0] - projected[0], point[1] - projected[1])
            if distance < closest_distance:
                closest_index, closest_distance = index, distance
        threshold_raw = max(14, round(22 / self.scale))
        return closest_index if closest_distance <= threshold_raw else None

    def _start_polygon(self) -> None:
        if self.active_role == "ir_association":
            self.status = "IR association edits the selected road segment; select one and press E."
            return
        role_regions = self._regions_for_active_role()
        sequence = len(role_regions) + 1
        role_name = self.active_role.replace("_", " ")
        self.drawing = {
            "region_id": f"draft_{self.active_role}_{sequence}",
            "name": f"Draft {role_name} {sequence}",
            "role": self.active_role,
            "coordinate_system": "RAW_CAMERA",
            "points": [],
            "initial_points": [],
            "editable": True,
            "status": "DRAFT_NEEDS_REVIEW",
            "routing_edge_id": None if self.active_role == "road_segment" else None,
            "ir_sensor": None if self.active_role == "road_segment" else None,
        }
        self.status = f"Click vertices for {self.drawing['name']}; Enter or right-click closes it."

    def _close_polygon(self) -> None:
        if self.drawing is None:
            return
        points = self.drawing["points"]
        errors = validate_polygon(points, self.image.shape[1], self.image.shape[0])
        if errors:
            self.status = "Cannot close polygon: " + "; ".join(errors)
            return
        if self.active_role == "hazard_polygon":
            building = next(
                (item for item in self.draft["regions"] if item.get("role") == "building_detection_roi"),
                None,
            )
            if building and any(not point_in_polygon(point, building["points"]) for point in points):
                self.status = "Hazard polygon must remain inside Building A detection ROI."
                return
        self._snapshot_undo()
        self.drawing["initial_points"] = deepcopy(points)
        self.draft["regions"].append(self.drawing)
        self.selected_region_id = self.drawing["region_id"]
        self.drawing = None
        self.status = "Polygon added to draft. Validate before saving."

    def _add_vertex_to_selected_edge(self, point: tuple[int, int]) -> None:
        region = self._region(self.selected_region_id)
        if region is None or not region.get("editable", False):
            self.status = "Select an editable draft polygon first."
            return
        edge_index = self._nearest_edge(point, region)
        if edge_index is None:
            self.status = "Shift+Click closer to a polygon edge to insert a vertex."
            return
        self._snapshot_undo()
        region["points"].insert(edge_index + 1, [point[0], point[1]])
        region["status"] = "DRAFT_NEEDS_REVIEW"
        self.selected_vertex = edge_index + 1
        self.status = "Vertex inserted; RAW_CAMERA coordinates retained."

    def _select_at(self, point: tuple[int, int]) -> None:
        editable_regions = [
            region
            for region in reversed(self.draft.get("regions", []))
            if region.get("editable", False) and region.get("points")
        ]
        for region in editable_regions:
            nearest = self._nearest_vertex(point, region)
            if nearest is not None:
                self.selected_region_id = region["region_id"]
                self.selected_vertex = nearest[0]
                self.active_role = region["role"]
                self.drag_vertex = (region["region_id"], nearest[0])
                self._snapshot_undo()
                self.status = f"Moving vertex {nearest[0]} of {region['name']}."
                return
            if len(region["points"]) >= 3 and point_in_polygon(point, region["points"]):
                self.selected_region_id = region["region_id"]
                self.selected_vertex = None
                self.active_role = region["role"]
                self.status = f"Selected {region['name']}. Drag a vertex or Shift+Click an edge."
                return
        self.selected_region_id = None
        self.selected_vertex = None
        self.status = "No draft polygon selected. Press N to draw the active type."

    def _mouse(self, event: int, x: int, y: int, flags: int, _param: Any) -> None:
        point = self._display_to_raw(x, y)
        if point is not None:
            self.cursor_raw = point
        if event == cv2.EVENT_MOUSEMOVE and self.drag_vertex is not None and point is not None:
            region_id, vertex_index = self.drag_vertex
            region = self._region(region_id)
            if region is not None and vertex_index < len(region["points"]):
                region["points"][vertex_index] = [point[0], point[1]]
                region["status"] = "DRAFT_NEEDS_REVIEW"
            return
        if event == cv2.EVENT_LBUTTONDOWN and point is not None:
            if self.drawing is not None:
                self._snapshot_undo()
                self.drawing["points"].append([point[0], point[1]])
                return
            if flags & cv2.EVENT_FLAG_SHIFTKEY:
                self._add_vertex_to_selected_edge(point)
                return
            self._select_at(point)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drag_vertex = None
        elif event == cv2.EVENT_RBUTTONDOWN and self.drawing is not None:
            self._close_polygon()

    def _undo(self) -> None:
        if not self.undo_stack:
            self.status = "Nothing to undo."
            return
        self.draft, self.drawing = self.undo_stack.pop()
        if self.selected_region_id and self._region(self.selected_region_id) is None:
            self.selected_region_id = None
        self.status = "Last geometry edit undone."

    def _reset_selected(self) -> None:
        region = self._region(self.selected_region_id)
        if region is None or not region.get("editable", False):
            self.status = "Select one editable draft ROI to reset."
            return
        self._snapshot_undo()
        initial = region.get("initial_points", [])
        if initial:
            region["points"] = deepcopy(initial)
            region["status"] = "DRAFT_NEEDS_REVIEW"
            self.status = f"Reset {region['name']} to its initial draft geometry."
        else:
            self.draft["regions"] = [item for item in self.draft["regions"] if item is not region]
            self.selected_region_id = None
            self.status = "Removed draft polygon with no initial geometry."
        self.selected_vertex = None

    def _delete_vertex(self) -> None:
        region = self._region(self.selected_region_id)
        if region is None or self.selected_vertex is None:
            self.status = "Select a polygon vertex, then press X to delete it."
            return
        self._snapshot_undo()
        points = region["points"]
        if 0 <= self.selected_vertex < len(points):
            points.pop(self.selected_vertex)
            region["status"] = "DRAFT_NEEDS_REVIEW"
        self.selected_vertex = None
        self.status = "Vertex deleted; polygon may be invalid until repaired."

    def _cycle_ir_association(self) -> None:
        region = self._region(self.selected_region_id)
        if region is None or region.get("role") != "road_segment":
            self.status = "Select a road segment before changing its IR association."
            return
        self._snapshot_undo()
        values = [None, "IR_A", "IR_B"]
        current = region.get("ir_sensor")
        region["ir_sensor"] = values[(values.index(current) + 1) % len(values)] if current in values else None
        region["status"] = "DRAFT_NEEDS_REVIEW"
        if region["ir_sensor"]:
            self.draft["ir_associations"][region["ir_sensor"]] = {
                "road_region_id": region["region_id"],
                "status": "NEEDS PHYSICAL CONFIRMATION",
            }
            self.status = f"Draft {region['ir_sensor']} association set; physical confirmation is still required."
        else:
            for sensor, association in self.draft["ir_associations"].items():
                if association.get("road_region_id") == region["region_id"]:
                    association["road_region_id"] = None
                    association["status"] = "NEEDS PHYSICAL CONFIRMATION"
            self.status = "Removed draft IR association."

    def _reload(self) -> None:
        if not self.draft_path.exists():
            self.status = f"No saved draft at {self.draft_path}."
            return
        self.draft = load_draft(self.draft_path)
        self.undo_stack.clear()
        self.drawing = None
        self.selected_region_id = None
        self.selected_vertex = None
        self.status = "Saved draft reloaded."

    def _save(self) -> None:
        validation = validate_draft(self.draft)
        if not validation["passed"]:
            self.status = "Save blocked: " + "; ".join(validation["errors"][:2])
            return
        self.draft["last_saved_at_utc"] = datetime.now(timezone.utc).isoformat()
        backup = save_draft(self.draft, self.draft_path)
        self.status = "Draft saved; production settings unchanged."
        if backup:
            self.status += f" Backup: {backup.name}"

    def _new_region(self) -> None:
        if self.drawing is not None:
            self.status = "Finish or undo the active polygon before starting another."
            return
        self._start_polygon()

    def _handle_key(self, key: int) -> bool:
        if key in (ord("q"), ord("Q"), 27):
            return False
        if key in CATEGORY_KEYS:
            self.active_role = CATEGORY_KEYS[key]
            self.status = f"Active type: {CATEGORY_LABELS[self.active_role]}. Press N to draw."
        elif key in (ord("n"), ord("N")):
            self._new_region()
        elif key in (10, 13) and self.drawing is not None:
            self._close_polygon()
        elif key in (ord("u"), ord("U")):
            self._undo()
        elif key in (ord("r"), ord("R")):
            self._reset_selected()
        elif key in (ord("x"), ord("X"), 127, 8):
            self._delete_vertex()
        elif key in (ord("s"), ord("S")):
            self._save()
        elif key in (ord("l"), ord("L")):
            self._reload()
        elif key in (ord("p"), ord("P")):
            self.show_existing = not self.show_existing
            self.status = "Comparison overlay " + ("ON" if self.show_existing else "OFF")
        elif key in (ord("e"), ord("E")):
            self._cycle_ir_association()
        elif key in (9,):  # Tab cycles editable polygons for the selected category.
            candidates = self._regions_for_active_role()
            if candidates:
                current = next(
                    (index for index, item in enumerate(candidates) if item["region_id"] == self.selected_region_id),
                    -1,
                )
                selected = candidates[(current + 1) % len(candidates)]
                self.selected_region_id = selected["region_id"]
                self.selected_vertex = None
                self.status = f"Selected {selected['name']}."
        return True

    def run(self) -> int:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(WINDOW_NAME, PREVIEW_SIZE[0], PREVIEW_SIZE[1])
        cv2.setMouseCallback(WINDOW_NAME, self._mouse)
        try:
            while True:
                rendered = render_draft(
                    self.image,
                    self.draft,
                    show_existing=self.show_existing,
                    status=self.status,
                    selected_region_id=self.selected_region_id,
                    selected_vertex=self.selected_vertex,
                    drawing_points=self.drawing["points"] if self.drawing else None,
                    cursor_raw=self.cursor_raw,
                )
                preview, _ = fit_image_for_display(rendered, PREVIEW_SIZE)
                cv2.imshow(WINDOW_NAME, preview)
                key = cv2.waitKey(20) & 0xFF
                if key != 0xFF and not self._handle_key(key):
                    break
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            cv2.destroyAllWindows()
        return 0


def _print_validation(draft: dict[str, Any], validation: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "passed": validation["passed"],
                "status": draft.get("status"),
                "coordinate_system": draft.get("coordinate_system"),
                "image_size": draft.get("image_size"),
                "region_count": len(draft.get("regions", [])),
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "routing_edge_mappings": draft.get("routing_edge_mappings"),
                "ir_associations": draft.get("ir_associations"),
            },
            indent=2,
        )
    )


def main() -> int:
    args = parse_args()
    image_path = args.image.resolve() if args.image else find_latest_raw_image()
    image, image_metadata = load_reference(image_path)
    if image.shape[:2] != (1080, 1920):
        print(
            f"Reference is {image.shape[1]}x{image.shape[0]}; expected native 1920x1080.",
            file=sys.stderr,
        )
        return 2

    if args.initialize or args.force_reinitialize or not args.draft.exists():
        source_configuration, legacy_regions = load_canonical_roi_configuration()
        draft = build_initial_draft(
            image_path,
            image,
            image_metadata,
            source_configuration,
            legacy_regions,
        )
        if args.initialize and args.draft.exists() and not args.force_reinitialize:
            print(f"Draft already exists; use --force-reinitialize to preserve it as .bak: {args.draft}", file=sys.stderr)
            return 2
        if args.initialize or args.force_reinitialize:
            backup = save_draft(draft, args.draft) if args.draft.exists() else None
            if backup:
                print(f"Previous draft backup: {backup}")
            if not args.draft.exists():
                save_draft(draft, args.draft)
    else:
        try:
            draft = load_draft(args.draft)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Unable to load draft: {exc}", file=sys.stderr)
            return 2

    validation = validate_draft(draft)
    if args.validate_only:
        _print_validation(draft, validation)
        return 0 if validation["passed"] else 1
    if args.render_to:
        rendered = render_draft(image, draft)
        args.render_to.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.render_to), rendered):
            print(f"Unable to write annotated preview: {args.render_to}", file=sys.stderr)
            return 1
        print(f"Annotated draft preview: {args.render_to.resolve()}")
        _print_validation(draft, validation)
        return 0 if validation["passed"] else 1
    if args.initialize or args.force_reinitialize:
        rendered = render_draft(image, draft)
        DEFAULT_ANNOTATED_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(DEFAULT_ANNOTATED_PATH), rendered):
            print(f"Unable to write annotated preview: {DEFAULT_ANNOTATED_PATH}", file=sys.stderr)
            return 1
        print(f"Draft created: {args.draft.resolve()}")
        print(f"Annotated preview: {DEFAULT_ANNOTATED_PATH.resolve()}")
        _print_validation(draft, validation)
        return 0 if validation["passed"] else 1
    if not validation["passed"]:
        _print_validation(draft, validation)
        print("Edit geometry until valid before saving.", file=sys.stderr)
        return 1
    print(f"Opening draft editor for {image_path}")
    print("Draft-only mode: no .env, production ROI, inference, MQTT, or actuator calls are made.")
    return ROIEditor(image, draft, args.draft).run()


if __name__ == "__main__":
    raise SystemExit(main())
