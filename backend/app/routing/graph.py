"""Read-only active routing graph projection."""

from datetime import datetime, timezone
from typing import Any

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.cost import EdgeCostResult
from app.routing.safety import EdgeSafetyDecision
from app.routing.topology import RoutingTopology


class ActiveRoutingGraphProjection(BaseModel):
    """Derived graph containing only explicitly routable edges."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    graph: nx.MultiDiGraph
    included_edge_ids: list[str] = Field(default_factory=list)
    excluded_edge_ids: list[str] = Field(default_factory=list)
    unresolved_edge_ids: list[str] = Field(default_factory=list)
    missing_cost_edge_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def build_active_routing_graph(
    topology: RoutingTopology,
    safety_decisions: list[EdgeSafetyDecision],
    cost_results: list[EdgeCostResult],
) -> ActiveRoutingGraphProjection:
    """Project a validated topology into a routable MultiDiGraph."""

    topology_edge_ids = {edge.edge_id for edge in topology.edges}
    _validate_topology(topology)
    safety_by_id = _index_inputs(
        safety_decisions,
        "safety",
        topology_edge_ids,
        lambda item: item.edge_id,
    )
    cost_by_id = _index_inputs(
        cost_results,
        "cost",
        topology_edge_ids,
        lambda item: item.edge_id,
    )

    graph = nx.MultiDiGraph()
    for node in topology.nodes:
        graph.add_node(
            node.node_id,
            label=node.label,
            coordinates=node.coordinates.model_dump(mode="json")
            if node.coordinates is not None
            else None,
            metadata=dict(node.metadata),
        )

    included: list[str] = []
    excluded: list[str] = []
    unresolved: list[str] = []
    missing_cost: list[str] = []
    reasons: list[str] = []
    warnings = list(topology.validation_warnings)
    audits: list[FusionSourceReference] = []

    for edge in topology.edges:
        safety = safety_by_id.get(edge.edge_id)
        cost = cost_by_id.get(edge.edge_id)
        if safety is not None:
            audits.extend(safety.audit_references)
        if cost is not None:
            audits.extend(cost.audit_references)

        if safety is None or safety.exclude_from_active_graph is None:
            unresolved.append(edge.edge_id)
            reasons.append(f"edge {edge.edge_id} safety exclusion is unresolved")
        elif safety.exclude_from_active_graph is True:
            excluded.append(edge.edge_id)
            reasons.append(f"edge {edge.edge_id} excluded by safety decision")
        elif cost is None:
            missing_cost.append(edge.edge_id)
            reasons.append(f"edge {edge.edge_id} has no cost result")
        elif cost.status != "calculated" or cost.edge_cost is None or cost.edge_cost <= 0:
            missing_cost.append(edge.edge_id)
            reasons.append(f"edge {edge.edge_id} has no valid calculated cost")
        else:
            _add_edge(graph, edge, cost)
            included.append(edge.edge_id)

    return ActiveRoutingGraphProjection(
        graph=graph,
        included_edge_ids=included,
        excluded_edge_ids=excluded,
        unresolved_edge_ids=unresolved,
        missing_cost_edge_ids=missing_cost,
        reasons=reasons,
        warnings=warnings,
        generated_at=datetime.now(timezone.utc),
        audit_references=audits,
    )


def _add_edge(graph: nx.MultiDiGraph, edge: Any, cost: EdgeCostResult) -> None:
    attributes = {
        "edge_id": edge.edge_id,
        "distance_cm": cost.distance_cm,
        "edge_cost": cost.edge_cost,
        "road_roi_name": edge.road_roi_name,
        "O": cost.o,
        "L": cost.l,
        "routing_c": cost.routing_c,
        "weighted_risk": cost.weighted_risk,
        "risk_multiplier": cost.risk_multiplier,
    }
    graph.add_edge(edge.from_node, edge.to_node, key=edge.edge_id, **attributes)
    if edge.bidirectional:
        graph.add_edge(edge.to_node, edge.from_node, key=edge.edge_id, **attributes)


def _index_inputs(items: list[Any], label: str, known_ids: set[str], key_getter: Any) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for item in items:
        item_id = key_getter(item)
        if item_id is None or item_id not in known_ids:
            raise ValueError(f"{label} input references unknown edge {item_id}")
        if item_id in indexed:
            raise ValueError(f"duplicate {label} input for edge {item_id}")
        indexed[item_id] = item
    return indexed


def _validate_topology(topology: RoutingTopology) -> None:
    node_ids = {node.node_id for node in topology.nodes}
    edge_ids: set[str] = set()
    for edge in topology.edges:
        if edge.edge_id in edge_ids:
            raise ValueError(f"duplicate topology edge {edge.edge_id}")
        edge_ids.add(edge.edge_id)
        if edge.from_node not in node_ids or edge.to_node not in node_ids:
            raise ValueError(f"topology edge {edge.edge_id} references unknown node")
