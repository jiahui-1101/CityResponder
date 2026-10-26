"""Opt-in adapter for RAW_CAMERA polygon ROI calibration drafts.

The adapter deliberately keeps draft coordinates as the source of truth and
translates points by the board-crop origin once. S2 owns any shared junction
pixels for occupancy accounting; this is a pixel-counting convention only and
does not imply graph topology or right of way.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from app.vision.schemas import CoordinateSystem, PolygonPoint, PolygonROI, ROI


class PolygonROIConfigError(ValueError):
    """Raised when an explicitly selected polygon ROI draft is unsafe to use."""


@dataclass(frozen=True)
class PolygonRegion:
    region_id: str
    label: str
    raw_points: tuple[tuple[float, float], ...]
    board_points: tuple[tuple[float, float], ...]

    def as_polygon_roi(self) -> PolygonROI:
        return PolygonROI(
            name=self.label,
            points=[PolygonPoint(x=x, y=y) for x, y in self.board_points],
            coordinate_system=CoordinateSystem.RAW_BOARD_CROP,
        )

    def bounding_roi(self) -> ROI:
        xs = [point[0] for point in self.board_points]
        ys = [point[1] for point in self.board_points]
        x1, y1 = math.floor(min(xs)), math.floor(min(ys))
        x2, y2 = math.ceil(max(xs)), math.ceil(max(ys))
        return ROI(
            name=self.label,
            x=x1,
            y=y1,
            width=x2 - x1 + 1,
            height=y2 - y1 + 1,
        )


@dataclass(frozen=True)
class PolygonROIConfiguration:
    path: Path
    status: str
    source_width: int
    source_height: int
    crop: ROI
    building: PolygonRegion
    hazard: PolygonRegion
    road_domain: PolygonRegion
    road_segments: tuple[PolygonRegion, ...]
    exclusions: tuple[PolygonRegion, ...]
    junction_owner_region_id: str
    junction_raw_regions: tuple[tuple[tuple[float, float], ...], ...]

    def road_masks(self, frame_shape: tuple[int, ...]) -> list["RoadRegionMask"]:
        """Rasterize exclusions and return mutually exclusive board-frame masks."""

        height, width = frame_shape[:2]
        if (width, height) != (self.crop.width, self.crop.height):
            raise PolygonROIConfigError(
                "board frame shape does not match the configured processing crop"
            )
        domain = rasterize_polygon(self.road_domain.board_points, width, height)
        excluded = np.zeros((height, width), dtype=np.uint8)
        for region in self.exclusions:
            excluded |= rasterize_polygon(region.board_points, width, height)
        domain[excluded != 0] = 0

        by_id = {region.region_id: region for region in self.road_segments}
        if self.junction_owner_region_id not in by_id:
            raise PolygonROIConfigError(
                f"junction owner {self.junction_owner_region_id!r} is not a road segment"
            )
        ordered = [by_id[self.junction_owner_region_id]] + [
            region
            for region in self.road_segments
            if region.region_id != self.junction_owner_region_id
        ]
        claimed = np.zeros((height, width), dtype=np.uint8)
        output: list[RoadRegionMask] = []
        for region in ordered:
            candidate = rasterize_polygon(region.board_points, width, height)
            candidate[domain == 0] = 0
            candidate[claimed != 0] = 0
            if not np.any(candidate):
                raise PolygonROIConfigError(
                    f"road region {region.region_id!r} has no valid pixels after exclusions"
                )
            claimed |= candidate
            output.append(
                RoadRegionMask(
                    region=region,
                    roi=region.bounding_roi(),
                    valid_mask=candidate,
                )
            )
        return output


@dataclass(frozen=True)
class RoadRegionMask:
    region: PolygonRegion
    roi: ROI
    valid_mask: np.ndarray


def load_polygon_roi_config(
    path: str | Path | None,
    *,
    expected_resolution: tuple[int, int],
) -> PolygonROIConfiguration:
    """Load schema-v1 calibration draft without changing it or inferring edges."""

    if path is None or not str(path).strip():
        raise PolygonROIConfigError(
            "polygon ROI mode is enabled but VISION_POLYGON_ROI_CONFIG_PATH is unset"
        )
    config_path = resolve_config_path(path)
    try:
        draft = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PolygonROIConfigError(f"unable to read polygon ROI config: {config_path}") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PolygonROIConfigError(f"invalid polygon ROI JSON: {config_path}") from exc

    if not isinstance(draft, dict):
        raise PolygonROIConfigError("polygon ROI config root must be an object")
    schema_version = draft.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
        raise PolygonROIConfigError("unsupported polygon ROI schema_version; expected 1")
    if draft.get("coordinate_system") != CoordinateSystem.RAW_CAMERA.value:
        raise PolygonROIConfigError("polygon ROI config must use RAW_CAMERA coordinates")
    status = str(draft.get("status", ""))
    if status != "DRAFT_NOT_PRODUCTION_ACTIVE":
        raise PolygonROIConfigError(
            "polygon ROI config must remain marked DRAFT_NOT_PRODUCTION_ACTIVE"
        )

    image_size = draft.get("image_size")
    if not isinstance(image_size, dict):
        raise PolygonROIConfigError("image_size must be an object")
    source_width = _positive_int(image_size.get("width"), "image_size.width")
    source_height = _positive_int(image_size.get("height"), "image_size.height")
    if (source_width, source_height) != expected_resolution:
        raise PolygonROIConfigError(
            f"polygon config is {source_width}x{source_height}, expected "
            f"{expected_resolution[0]}x{expected_resolution[1]} RAW_CAMERA"
        )

    regions = draft.get("regions")
    if not isinstance(regions, list):
        raise PolygonROIConfigError("polygon ROI config regions must be a list")
    region_by_role: dict[str, list[dict[str, Any]]] = {}
    ids: set[str] = set()
    points_by_id: dict[str, tuple[tuple[float, float], ...]] = {}
    for region in regions:
        if not isinstance(region, dict):
            raise PolygonROIConfigError("each polygon ROI region must be an object")
        region_id = str(region.get("region_id", "")).strip()
        if not region_id or region_id in ids:
            raise PolygonROIConfigError("polygon ROI region IDs must be unique and nonblank")
        ids.add(region_id)
        if region.get("coordinate_system", CoordinateSystem.RAW_CAMERA.value) != CoordinateSystem.RAW_CAMERA.value:
            raise PolygonROIConfigError(
                f"region {region_id!r} must use RAW_CAMERA coordinates"
            )
        region_by_role.setdefault(str(region.get("role", "")), []).append(region)
        points_by_id[region_id] = _validated_points(region, source_width, source_height)

    crop_raw = _one_region(region_by_role, "processing_crop")
    building_raw = _one_region(region_by_role, "building_detection_roi")
    hazard_raw = _one_region(region_by_role, "hazard_polygon")
    road_raw = _one_region(region_by_role, "road_segmentation_roi")
    segment_raw = region_by_role.get("road_segment", [])
    exclusion_raw = region_by_role.get("exclusion_mask", [])
    if not segment_raw:
        raise PolygonROIConfigError("at least one road_segment polygon is required")
    if len(exclusion_raw) < 2:
        raise PolygonROIConfigError("left and right support exclusion masks are required")
    if draft.get("routing_edge_mappings"):
        raise PolygonROIConfigError(
            "Phase A polygon mode must keep road-to-edge mappings empty"
        )

    crop_points = points_by_id[str(crop_raw["region_id"])]
    crop = _rectangular_crop(crop_raw, crop_points, source_width, source_height)
    crop_origin = (crop.x, crop.y)

    def region(item: dict[str, Any]) -> PolygonRegion:
        raw_points = points_by_id[str(item["region_id"])]
        board_points = tuple(raw_to_board_point(point, crop_origin) for point in raw_points)
        return PolygonRegion(
            region_id=str(item["region_id"]),
            label=_region_label(item),
            raw_points=raw_points,
            board_points=board_points,
        )

    building = region(building_raw)
    hazard = region(hazard_raw)
    road_domain = region(road_raw)
    road_segments = tuple(region(item) for item in segment_raw)
    exclusions = tuple(region(item) for item in exclusion_raw)

    for item in (building, hazard, road_domain, *road_segments):
        _require_contained(item.raw_points, crop_points, item.region_id)
    _require_polygon_mask_contained(road_domain, road_segments, crop.width, crop.height)

    integration = draft.get("phase_a_integration")
    if not isinstance(integration, dict):
        raise PolygonROIConfigError("phase_a_integration must be an object")
    if integration.get("junction_ownership_policy") != "owner_first_pixel_claim":
        raise PolygonROIConfigError(
            "phase_a_integration.junction_ownership_policy must be "
            "owner_first_pixel_claim"
        )
    owner = str(integration.get("junction_owner_region_id", "")).strip()
    if owner not in {item.region_id for item in road_segments}:
        raise PolygonROIConfigError("junction_owner_region_id must identify a road segment")
    junction_values = integration.get("junction_regions_raw")
    if junction_values is None and integration.get("junction_region_points_raw") is not None:
        junction_values = [{"points": integration["junction_region_points_raw"]}]
    if not isinstance(junction_values, list) or not junction_values:
        raise PolygonROIConfigError(
            "phase_a_integration.junction_regions_raw must contain polygon regions"
        )
    junction_regions_raw: list[tuple[tuple[float, float], ...]] = []
    for index, value in enumerate(junction_values):
        if not isinstance(value, dict):
            raise PolygonROIConfigError("each junction region must be an object")
        points = _points_from_value(value.get("points"), f"junction region {index + 1}")
        _validate_simple_polygon(points, f"junction region {index + 1}")
        _require_bounds(points, source_width, source_height, f"junction region {index + 1}")
        _require_contained(points, crop_points, f"junction region {index + 1}")
        junction_regions_raw.append(tuple(points))

    config = PolygonROIConfiguration(
        path=config_path,
        status=status,
        source_width=source_width,
        source_height=source_height,
        crop=crop,
        building=building,
        hazard=hazard,
        road_domain=road_domain,
        road_segments=road_segments,
        exclusions=exclusions,
        junction_owner_region_id=owner,
        junction_raw_regions=tuple(junction_regions_raw),
    )
    masks = config.road_masks((crop.height, crop.width, 3))
    if len(masks) != len(road_segments):
        raise PolygonROIConfigError("not all road segment masks were built")
    domain_mask = rasterize_polygon(road_domain.board_points, crop.width, crop.height)
    for index, raw_points in enumerate(config.junction_raw_regions):
        board_points = tuple(raw_to_board_point(point, crop_origin) for point in raw_points)
        junction_mask = rasterize_polygon(board_points, crop.width, crop.height)
        if np.any((junction_mask != 0) & (domain_mask == 0)):
            raise PolygonROIConfigError(
                f"junction region {index + 1} extends beyond road segmentation ROI"
            )
    for index, first in enumerate(masks):
        for second in masks[index + 1 :]:
            if np.any((first.valid_mask != 0) & (second.valid_mask != 0)):
                raise PolygonROIConfigError("road segment masks overlap after ownership policy")
    return config


def raw_to_board_point(
    point: tuple[float, float], crop_origin: tuple[int, int]
) -> tuple[float, float]:
    """Translate one RAW_CAMERA point into RAW_BOARD_CROP coordinates."""

    return point[0] - crop_origin[0], point[1] - crop_origin[1]


def board_to_raw_point(
    point: tuple[float, float], crop_origin: tuple[int, int]
) -> tuple[float, float]:
    """Inverse of raw_to_board_point; no scaling or letterboxing is involved."""

    return point[0] + crop_origin[0], point[1] + crop_origin[1]


def point_in_polygon(
    point: tuple[float, float], polygon: Iterable[tuple[float, float]]
) -> bool:
    """Ray-cast containment with boundary points treated as inside."""

    vertices = list(polygon)
    x, y = point
    inside = False
    for index, start in enumerate(vertices):
        end = vertices[(index + 1) % len(vertices)]
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def polygon_area(polygon: Iterable[tuple[float, float]]) -> float:
    points = list(polygon)
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def rasterize_polygon(
    polygon: Iterable[tuple[float, float]], width: int, height: int
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    points = np.asarray(list(polygon), dtype=np.float64)
    if len(points) < 3:
        return mask
    cv2.fillPoly(mask, [np.rint(points).astype(np.int32)], 1)
    return mask


def _rectangular_crop(
    item: dict[str, Any],
    points: tuple[tuple[float, float], ...],
    width: int,
    height: int,
) -> ROI:
    if len(points) != 4:
        raise PolygonROIConfigError("processing_crop must have four rectangle corners")
    xs, ys = {point[0] for point in points}, {point[1] for point in points}
    if len(xs) != 2 or len(ys) != 2:
        raise PolygonROIConfigError("processing_crop must be an axis-aligned rectangle")
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    expected_corners = {(x1, y1), (x1, y2), (x2, y1), (x2, y2)}
    if set(points) != expected_corners:
        raise PolygonROIConfigError(
            "processing_crop must contain each rectangle corner exactly once"
        )
    if any(value != int(value) for value in (x1, x2, y1, y2)):
        raise PolygonROIConfigError("processing_crop coordinates must be integer pixels")
    if x2 <= x1 or y2 <= y1 or x2 > width or y2 > height:
        raise PolygonROIConfigError("processing_crop is empty or outside source resolution")
    return ROI(
        name=_region_label(item) or "raw_board_crop",
        x=int(x1),
        y=int(y1),
        width=int(x2 - x1),
        height=int(y2 - y1),
    )


def _validated_points(
    item: dict[str, Any], width: int, height: int
) -> tuple[tuple[float, float], ...]:
    points = _points_from_value(item.get("points"), str(item.get("region_id", "region")))
    _validate_simple_polygon(points, str(item.get("region_id", "region")))
    _require_bounds(points, width, height, str(item.get("region_id", "region")))
    return tuple(points)


def _points_from_value(value: Any, label: str) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) < 3:
        raise PolygonROIConfigError(f"{label} must contain at least three points")
    output: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise PolygonROIConfigError(f"{label} contains an invalid point")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError) as exc:
            raise PolygonROIConfigError(f"{label} contains a nonnumeric point") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise PolygonROIConfigError(f"{label} contains a non-finite point")
        output.append((x, y))
    if len(set(output)) < 3:
        raise PolygonROIConfigError(f"{label} must contain at least three distinct points")
    return output


def _validate_simple_polygon(points: Iterable[tuple[float, float]], label: str) -> None:
    vertices = list(points)
    count = len(vertices)
    for first_index in range(count):
        first_start = vertices[first_index]
        first_end = vertices[(first_index + 1) % count]
        for second_index in range(first_index + 1, count):
            if second_index in {first_index, (first_index + 1) % count}:
                continue
            if first_index == 0 and second_index == count - 1:
                continue
            second_start = vertices[second_index]
            second_end = vertices[(second_index + 1) % count]
            if _segments_intersect(first_start, first_end, second_start, second_end):
                raise PolygonROIConfigError(f"{label} is self-intersecting")
    if polygon_area(vertices) <= 0.5:
        raise PolygonROIConfigError(f"{label} has zero or negligible area")


def _require_bounds(
    points: Iterable[tuple[float, float]], width: int, height: int, label: str
) -> None:
    if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
        raise PolygonROIConfigError(f"{label} has points outside {width}x{height} source bounds")


def _require_contained(
    points: Iterable[tuple[float, float]],
    crop: tuple[tuple[float, float], ...],
    label: str,
) -> None:
    xs = [point[0] for point in crop]
    ys = [point[1] for point in crop]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    # numpy frame slices are half-open: their right and bottom coordinates do
    # not represent included pixels. ROI vertices on those edges would be clipped.
    if any(not (x1 <= x < x2 and y1 <= y < y2) for x, y in points):
        raise PolygonROIConfigError(f"{label} is not contained by processing_crop")


def _require_polygon_mask_contained(
    domain: PolygonRegion,
    segments: tuple[PolygonRegion, ...],
    width: int,
    height: int,
) -> None:
    domain_mask = rasterize_polygon(domain.board_points, width, height)
    for segment in segments:
        segment_mask = rasterize_polygon(segment.board_points, width, height)
        if np.any((segment_mask != 0) & (domain_mask == 0)):
            raise PolygonROIConfigError(
                f"road segment {segment.region_id!r} extends beyond road segmentation ROI"
            )


def _one_region(by_role: dict[str, list[dict[str, Any]]], role: str) -> dict[str, Any]:
    matches = by_role.get(role, [])
    if len(matches) != 1:
        raise PolygonROIConfigError(f"expected exactly one {role} region, found {len(matches)}")
    return matches[0]


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PolygonROIConfigError(f"{label} must be a positive integer")
    return value


def _region_label(item: dict[str, Any]) -> str:
    label = str(item.get("label", "")).strip()
    if label:
        # S1/S2/S3 labels retain stable ROI names without implying graph IDs.
        return label.split("—", 1)[0].strip()
    return str(item.get("name", item.get("region_id", "region"))).strip()


def resolve_config_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.exists():
        return candidate.resolve()
    project_root = Path(__file__).resolve().parents[3]
    return (project_root / candidate).resolve()


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    epsilon: float = 1e-9,
) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > epsilon:
        return False
    return (
        min(x1, x2) - epsilon <= px <= max(x1, x2) + epsilon
        and min(y1, y2) - epsilon <= py <= max(y1, y2) + epsilon
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    epsilon = 1e-9
    if ((o1 > epsilon and o2 < -epsilon) or (o1 < -epsilon and o2 > epsilon)) and (
        (o3 > epsilon and o4 < -epsilon) or (o3 < -epsilon and o4 > epsilon)
    ):
        return True
    return (
        (abs(o1) <= epsilon and _point_on_segment(c, a, b))
        or (abs(o2) <= epsilon and _point_on_segment(d, a, b))
        or (abs(o3) <= epsilon and _point_on_segment(a, c, d))
        or (abs(o4) <= epsilon and _point_on_segment(b, c, d))
    )
