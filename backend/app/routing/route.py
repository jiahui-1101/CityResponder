"""Deterministic A* route calculation over the active routing graph."""

from datetime import datetime, timezone
from time import perf_counter
from typing import Protocol

import networkx as nx
from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.graph import ActiveRoutingGraphProjection


class RoutingHeuristicPolicy(Protocol):
    """Caller-supplied admissible heuristic for the configured graph."""

    def estimate(
        self,
        node_id: str,
        destination_node_id: str,
        graph: nx.DiGraph,
    ) -> float:
        """Return a non-negative heuristic estimate."""


class RouteCalculationResult(BaseModel):
    """Auditable route result without dispatch or route persistence."""

    status: str
    source_node_id: str
    destination_node_id: str
    node_path: list[str] = Field(default_factory=list)
    edge_path: list[str] = Field(default_factory=list)
    total_edge_cost: float | None = None
    total_distance_cm: float | None = None
    no_safe_route: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    calculation_duration_ms: float
    calculated_at: datetime
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def calculate_route(
    projection: ActiveRoutingGraphProjection,
    source_node_id: str,
    destination_node_id: str,
    *,
    heuristic_policy: RoutingHeuristicPolicy | None = None,
    allow_same_node: bool = False,
) -> RouteCalculationResult:
    """Calculate one route using existing active-edge costs only."""

    started = perf_counter()
    reasons: list[str] = []
    if not source_node_id or not destination_node_id:
        reasons.append("source_node_id and destination_node_id are required")
    if source_node_id == destination_node_id and not allow_same_node:
        reasons.append("source and destination nodes must be distinct")

    graph = projection.graph
    if graph is None or not isinstance(graph, nx.MultiDiGraph):
        reasons.append("active routing graph is unavailable")
    elif source_node_id not in graph or destination_node_id not in graph:
        reasons.append("source or destination node is not present in the active graph")

    if reasons:
        return _result(
            status="invalid_configuration",
            source=source_node_id,
            destination=destination_node_id,
            reasons=reasons,
            node_path=[],
            edge_path=[],
            total_cost=None,
            total_distance=None,
            started=started,
            projection=projection,
        )

    simple_graph, selected_edges = _collapse_parallel_edges(graph)
    heuristic = _heuristic(heuristic_policy, destination_node_id, simple_graph)
    try:
        node_path = nx.astar_path(
            simple_graph,
            source_node_id,
            destination_node_id,
            heuristic=heuristic,
            weight="edge_cost",
        )
    except nx.NetworkXNoPath:
        return _result(
            status="NO_SAFE_ROUTE",
            source=source_node_id,
            destination=destination_node_id,
            reasons=["no path exists in the active routing graph"],
            node_path=[],
            edge_path=[],
            total_cost=None,
            total_distance=None,
            started=started,
            projection=projection,
        )

    edge_path: list[str] = []
    total_cost = 0.0
    total_distance = 0.0
    for from_node, to_node in zip(node_path, node_path[1:]):
        selected = selected_edges[(from_node, to_node)]
        edge_path.append(selected["edge_id"])
        total_cost += selected["edge_cost"]
        total_distance += selected["distance_cm"]
    return _result(
        status="route_found",
        source=source_node_id,
        destination=destination_node_id,
        reasons=[],
        node_path=[str(node) for node in node_path],
        edge_path=edge_path,
        total_cost=total_cost,
        total_distance=total_distance,
        started=started,
        projection=projection,
    )


def _collapse_parallel_edges(
    graph: nx.MultiDiGraph,
) -> tuple[nx.DiGraph, dict[tuple[str, str], dict[str, float | str]]]:
    simple = nx.DiGraph()
    selected_edges: dict[tuple[str, str], dict[str, float | str]] = {}
    simple.add_nodes_from(graph.nodes)
    for from_node, to_node, _key, attributes in graph.edges(
        keys=True, data=True
    ):
        required = ("edge_id", "edge_cost", "distance_cm")
        if any(attributes.get(name) is None for name in required):
            continue
        candidate = {
            "edge_id": str(attributes["edge_id"]),
            "edge_cost": float(attributes["edge_cost"]),
            "distance_cm": float(attributes["distance_cm"]),
        }
        pair = (from_node, to_node)
        current = selected_edges.get(pair)
        if current is None or (
            candidate["edge_cost"], candidate["edge_id"]
        ) < (current["edge_cost"], current["edge_id"]):
            selected_edges[pair] = candidate
            simple.add_edge(from_node, to_node, **candidate)
    return simple, selected_edges


def _heuristic(
    policy: RoutingHeuristicPolicy | None,
    destination: str,
    graph: nx.DiGraph,
):
    if policy is None:
        return lambda _node, _target: 0.0

    def estimate(node: str, _target: str) -> float:
        value = float(policy.estimate(str(node), destination, graph))
        if value < 0.0:
            raise ValueError("routing heuristic must be non-negative")
        return value

    return estimate


def _result(
    *,
    status: str,
    source: str,
    destination: str,
    reasons: list[str],
    node_path: list[str],
    edge_path: list[str],
    total_cost: float | None,
    total_distance: float | None,
    started: float,
    projection: ActiveRoutingGraphProjection,
) -> RouteCalculationResult:
    return RouteCalculationResult(
        status=status,
        source_node_id=source,
        destination_node_id=destination,
        node_path=node_path,
        edge_path=edge_path,
        total_edge_cost=total_cost,
        total_distance_cm=total_distance,
        no_safe_route=status == "NO_SAFE_ROUTE",
        reasons=reasons,
        calculation_duration_ms=(perf_counter() - started) * 1000.0,
        calculated_at=datetime.now(timezone.utc),
        audit_references=list(projection.audit_references),
    )
