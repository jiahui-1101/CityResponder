"""Grounded graph-to-image mapping for read-only route visualization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field


class ImagePoint(BaseModel):
    x: float
    y: float
    normalized_x: float = Field(ge=0.0, le=1.0)
    normalized_y: float = Field(ge=0.0, le=1.0)


class NodeGeometry(BaseModel):
    node_id: str
    position: ImagePoint
    verification_status: str


class EdgeGeometry(BaseModel):
    edge_id: str
    from_node: str
    to_node: str
    points: list[ImagePoint]
    verification_status: str
    gate_dependency: str | None = None


class RouteImageGeometry(BaseModel):
    graph_version: str
    image_geometry_version: str
    status: str
    coordinate_system: str
    image_width: int
    image_height: int
    image_asset: str
    image_source: str
    nodes: dict[str, NodeGeometry]
    edges: dict[str, EdgeGeometry]
    warnings: list[str]


class RouteOverlayGeometry(BaseModel):
    selected_node_ids: list[str]
    selected_edge_ids: list[str]
    selected_points: list[ImagePoint]
    origin: ImagePoint | None
    destination: ImagePoint | None
    missing_edge_ids: list[str]
    continuous: bool
    mapping_duration_ms: float


def load_route_image_geometry(graph_path: Path, *, image_asset: str) -> RouteImageGeometry:
    """Load only documented draft coordinates; never infer missing geometry."""

    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    width, height = int(payload["image_size"]["width"]), int(payload["image_size"]["height"])
    if width <= 0 or height <= 0:
        raise ValueError("graph image dimensions must be positive")
    nodes = {
        item["node_id"]: NodeGeometry(
            node_id=item["node_id"],
            position=_point(item["position"], width, height),
            verification_status=item["verification_status"],
        )
        for item in payload["nodes"]
    }
    edges: dict[str, EdgeGeometry] = {}
    for item in payload["edges"]:
        edge_id = item["edge_id"]
        if item["from_node"] not in nodes or item["to_node"] not in nodes:
            raise ValueError(f"edge {edge_id} references unknown node")
        points = [_point(point, width, height) for point in item["centerline"]["points"]]
        if len(points) < 2:
            raise ValueError(f"edge {edge_id} requires at least two centerline points")
        _require_endpoint(points[0], nodes[item["from_node"]].position, edge_id)
        _require_endpoint(points[-1], nodes[item["to_node"]].position, edge_id)
        edges[edge_id] = EdgeGeometry(
            edge_id=edge_id,
            from_node=item["from_node"],
            to_node=item["to_node"],
            points=points,
            verification_status=item["verification_status"],
            gate_dependency=item.get("gate_dependency"),
        )
    digest = hashlib.sha256(graph_path.read_bytes()).hexdigest()[:16]
    return RouteImageGeometry(
        graph_version=f"phase-b1-final-review-draft:{digest}",
        image_geometry_version=f"raw-camera-1920x1080:{digest}",
        status=payload["status"],
        coordinate_system=payload["coordinate_system"],
        image_width=width,
        image_height=height,
        image_asset=image_asset,
        image_source=payload["reference_image"],
        nodes=nodes,
        edges=edges,
        warnings=[
            "DRAFT VISUAL ALIGNMENT — NOT PHYSICALLY VERIFIED",
            "Physical edge lengths and per-edge road ROI mapping remain unavailable",
            "PE07 gate position and physical-open feedback remain unverified",
        ],
    )


def map_route_to_image(geometry: RouteImageGeometry, node_ids: list[str], edge_ids: list[str]) -> RouteOverlayGeometry:
    """Map actual returned route IDs to an oriented continuous centerline."""

    started = perf_counter()
    if not node_ids and not edge_ids:
        return RouteOverlayGeometry(selected_node_ids=[], selected_edge_ids=[], selected_points=[], origin=None, destination=None, missing_edge_ids=[], continuous=True, mapping_duration_ms=(perf_counter()-started)*1000)
    if len(node_ids) != len(edge_ids) + 1:
        raise ValueError("route node/edge sequence lengths are inconsistent")
    missing = [edge_id for edge_id in edge_ids if edge_id not in geometry.edges]
    points: list[ImagePoint] = []
    continuous = not missing
    for index, edge_id in enumerate(edge_ids):
        edge = geometry.edges.get(edge_id)
        if edge is None:
            continue
        start, end = node_ids[index], node_ids[index + 1]
        if (start, end) == (edge.from_node, edge.to_node):
            oriented = edge.points
        elif (start, end) == (edge.to_node, edge.from_node):
            oriented = list(reversed(edge.points))
        else:
            raise ValueError(f"route edge {edge_id} does not connect {start} to {end}")
        if points and not _same(points[-1], oriented[0]):
            continuous = False
        points.extend(oriented if not points else oriented[1:])
    origin = geometry.nodes.get(node_ids[0]).position if node_ids and node_ids[0] in geometry.nodes else None
    destination = geometry.nodes.get(node_ids[-1]).position if node_ids and node_ids[-1] in geometry.nodes else None
    return RouteOverlayGeometry(selected_node_ids=node_ids, selected_edge_ids=edge_ids, selected_points=points, origin=origin, destination=destination, missing_edge_ids=missing, continuous=continuous, mapping_duration_ms=(perf_counter()-started)*1000)


def geometry_as_frontend_json(geometry: RouteImageGeometry) -> dict[str, Any]:
    return geometry.model_dump(mode="json")


def _point(payload: dict[str, Any], width: int, height: int) -> ImagePoint:
    x, y = float(payload["x"]), float(payload["y"])
    if not 0 <= x <= width or not 0 <= y <= height:
        raise ValueError(f"image coordinate ({x}, {y}) is outside {width}x{height}")
    return ImagePoint(x=x, y=y, normalized_x=x/width, normalized_y=y/height)


def _require_endpoint(actual: ImagePoint, expected: ImagePoint, edge_id: str) -> None:
    if abs(actual.x-expected.x) > 0.01 or abs(actual.y-expected.y) > 0.01:
        raise ValueError(f"edge {edge_id} centerline does not terminate at its documented node")


def _same(left: ImagePoint, right: ImagePoint) -> bool:
    return abs(left.x-right.x) <= 0.01 and abs(left.y-right.y) <= 0.01
