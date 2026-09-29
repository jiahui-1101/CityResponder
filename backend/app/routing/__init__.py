"""Part 4 routing evidence contracts."""

from app.routing.evidence import RoadEdgeEvidence, build_road_edge_evidence
from app.routing.topology import (
    RoutingCoordinates,
    RoutingEdge,
    RoutingNode,
    RoutingTopology,
    build_routing_topology,
)
from app.routing.factors import (
    RoutingFactorEvaluation,
    RoutingFactorPolicy,
    RoutingFactorValues,
    evaluate_routing_factors,
)
from app.routing.safety import (
    HARD_BLOCK_OCCUPANCY_THRESHOLD,
    REQUIRED_IR_SAMPLES,
    EdgeSafetyDecision,
    IRBlockagePolicy,
    IRSample,
    evaluate_edge_safety,
)
from app.routing.cost import (
    ROUTING_WEIGHTS,
    EdgeCostResult,
    calculate_edge_cost,
)
from app.routing.graph import (
    ActiveRoutingGraphProjection,
    build_active_routing_graph,
)
from app.routing.route import (
    RouteCalculationResult,
    RoutingHeuristicPolicy,
    calculate_route,
)
from app.routing.versioning import VersionedRoute, version_route
from app.routing.persistence import persist_versioned_route
from app.routing.projection import RouteProjection, get_route_history, get_route_projection
from app.routing.freshness import (
    TrafficCommandValidityResult,
    validate_traffic_command_route_version,
)

__all__ = [
    "RoadEdgeEvidence",
    "build_road_edge_evidence",
    "RoutingCoordinates",
    "RoutingEdge",
    "RoutingNode",
    "RoutingTopology",
    "build_routing_topology",
    "RoutingFactorEvaluation",
    "RoutingFactorPolicy",
    "RoutingFactorValues",
    "evaluate_routing_factors",
    "HARD_BLOCK_OCCUPANCY_THRESHOLD",
    "REQUIRED_IR_SAMPLES",
    "EdgeSafetyDecision",
    "IRBlockagePolicy",
    "IRSample",
    "evaluate_edge_safety",
    "ROUTING_WEIGHTS",
    "EdgeCostResult",
    "calculate_edge_cost",
    "ActiveRoutingGraphProjection",
    "build_active_routing_graph",
    "RouteCalculationResult",
    "RoutingHeuristicPolicy",
    "calculate_route",
    "VersionedRoute",
    "version_route",
    "persist_versioned_route",
    "RouteProjection",
    "get_route_history",
    "get_route_projection",
    "TrafficCommandValidityResult",
    "validate_traffic_command_route_version",
]
