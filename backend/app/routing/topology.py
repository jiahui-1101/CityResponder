"""Explicit physical routing topology and road-ROI mapping contracts."""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference


class RoutingCoordinates(BaseModel):
    """Optional physical coordinates supplied by explicit configuration."""

    x: float
    y: float


class RoutingNode(BaseModel):
    """One explicitly configured graph node."""

    node_id: str = Field(min_length=1)
    label: str | None = None
    coordinates: RoutingCoordinates | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class RoutingEdge(BaseModel):
    """One explicitly configured directed or bidirectional physical edge."""

    edge_id: str = Field(min_length=1)
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    distance_cm: float | None = Field(default=None, gt=0.0)
    road_roi_name: str | None = None
    bidirectional: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class RoutingTopology(BaseModel):
    """Validated graph definition without live evidence or routing weights."""

    nodes: list[RoutingNode]
    edges: list[RoutingEdge]
    road_roi_to_edge: dict[str, str] = Field(default_factory=dict)
    allow_self_edges: bool = False
    validation_warnings: list[str] = Field(default_factory=list)
    unavailable_tbd: list[str] = Field(default_factory=list)


def build_routing_topology(
    nodes: Sequence[RoutingNode],
    edges: Sequence[RoutingEdge],
    *,
    road_roi_to_edge: Mapping[str, str] | None = None,
    allow_self_edges: bool = False,
) -> RoutingTopology:
    """Build an explicit topology and reject invalid references or mappings."""

    node_list = list(nodes)
    edge_list = list(edges)
    node_ids = [node.node_id for node in node_list]
    edge_ids = [edge.edge_id for edge in edge_list]
    _require_unique(node_ids, "node IDs")
    _require_unique(edge_ids, "edge IDs")
    known_nodes = set(node_ids)
    known_edges = set(edge_ids)

    for edge in edge_list:
        if edge.from_node not in known_nodes or edge.to_node not in known_nodes:
            raise ValueError(f"edge {edge.edge_id} references an unknown node")
        if not allow_self_edges and edge.from_node == edge.to_node:
            raise ValueError(f"self-edge {edge.edge_id} is not permitted")
        if edge.distance_cm is not None and edge.distance_cm <= 0:
            raise ValueError(f"edge {edge.edge_id} distance_cm must be positive")

    mapping = dict(road_roi_to_edge or {})
    for roi_name, edge_id in mapping.items():
        if not roi_name.strip():
            raise ValueError("road ROI mapping names must not be blank")
        if edge_id not in known_edges:
            raise ValueError(
                f"road ROI {roi_name} maps to unknown edge {edge_id}"
            )

    edge_by_id = {edge.edge_id: edge for edge in edge_list}
    for edge in edge_list:
        if edge.road_roi_name is not None:
            mapped_edge = mapping.get(edge.road_roi_name)
            if mapped_edge is not None and mapped_edge != edge.edge_id:
                raise ValueError(
                    f"ROI {edge.road_roi_name} conflicts with edge {edge.edge_id}"
                )

    for roi_name, edge_id in mapping.items():
        edge = edge_by_id[edge_id]
        if edge.road_roi_name is None:
            edge_by_id[edge_id] = edge.model_copy(update={"road_roi_name": roi_name})

    warnings: list[str] = []
    unavailable: list[str] = []
    if not mapping:
        unavailable.append("road_roi_to_edge_mapping")
    if any(edge.distance_cm is None for edge in edge_list):
        unavailable.append("distance_cm_for_one_or_more_edges")

    return RoutingTopology(
        nodes=node_list,
        edges=[edge_by_id[edge.edge_id] for edge in edge_list],
        road_roi_to_edge=mapping,
        allow_self_edges=allow_self_edges,
        validation_warnings=warnings,
        unavailable_tbd=unavailable,
    )


def _require_unique(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
