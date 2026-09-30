"""Controlled timing evidence for the existing routing/respond pipeline."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.routing.cost import calculate_edge_cost
from app.routing.evidence import RoadEdgeEvidence
from app.routing.factors import RoutingFactorValues
from app.routing.graph import build_active_routing_graph
from app.routing.route import calculate_route
from app.routing.safety import EdgeSafetyDecision, evaluate_edge_safety, IRSample
from app.routing.topology import RoutingEdge, RoutingNode, build_routing_topology
from app.routing.versioning import version_route
from app.vision.schemas import FreshnessItem

from scripts.validate_e2e_cycle import ControlledFactorPolicy, ControlledIRPolicy, _run_scenario


ROOT = Path(__file__).resolve().parents[2]
JSON_REPORT = ROOT / "reports" / "validation" / "step18_response_timing.json"
MD_REPORT = ROOT / "reports" / "validation" / "step18_response_timing.md"


def _topology() -> object:
    nodes = [RoutingNode(node_id=node) for node in ("A", "B", "C", "D")]
    edges = [
        RoutingEdge(edge_id="e1", from_node="A", to_node="B", distance_cm=100, bidirectional=True, road_roi_name="r1"),
        RoutingEdge(edge_id="e2", from_node="B", to_node="D", distance_cm=100, bidirectional=True, road_roi_name="r2"),
        RoutingEdge(edge_id="e3", from_node="A", to_node="C", distance_cm=120, bidirectional=True, road_roi_name="r3"),
        RoutingEdge(edge_id="e4", from_node="C", to_node="D", distance_cm=120, bidirectional=True, road_roi_name="r4"),
    ]
    return build_routing_topology(nodes, edges, road_roi_to_edge={edge.road_roi_name: edge.edge_id for edge in edges})


def _evidence(edge: RoutingEdge, *, blocked: bool = False) -> RoadEdgeEvidence:
    now = datetime.now(timezone.utc)
    return RoadEdgeEvidence(
        road_edge_id=edge.edge_id, road_roi_name=edge.road_roi_name or edge.edge_id,
        frame_id=f"benchmark-{edge.edge_id}", frame_timestamp=now, frame_source="CAMERA",
        occupancy_ratio=.9 if blocked else .1, occupied_pixels=90 if blocked else 10,
        obstacle_count=1 if blocked else 0, max_obstacle_extent_px=20,
        mapped_ir_sensor="IR_A" if blocked else None, ir_timestamp=now if blocked else None,
        ir_value=True if blocked else None, time_delta_ms=1 if blocked else None,
        time_matched=True if blocked else None, conflict=False,
        conflict_reason="controlled benchmark fixture",
        freshness=FreshnessItem(source_type="road", source_id=edge.edge_id, available=True, stale=False, age_seconds=0, timestamp=now),
        available=True, stale=False,
    )


def _projection(topology, *, blocked_edges: set[str] = set()):
    safety = []
    costs = []
    for edge in topology.edges:
        blocked = edge.edge_id in blocked_edges
        evidence = _evidence(edge, blocked=blocked)
        samples = [IRSample(sensor_type="IR_A", timestamp=evidence.frame_timestamp, value=True) for _ in range(5)] if blocked else []
        decision = evaluate_edge_safety(evidence, samples, ir_policy=ControlledIRPolicy())
        factors = ControlledFactorPolicy().evaluate(evidence)
        from app.routing.factors import evaluate_routing_factors
        factor_result = evaluate_routing_factors(evidence, ControlledFactorPolicy())
        safety.append(decision)
        costs.append(calculate_edge_cost(edge, factor_result, decision))
    return build_active_routing_graph(topology, safety, costs)


def _route_sample(topology, *, blocked_edges: set[str] = set()):
    projection = _projection(topology, blocked_edges=blocked_edges)
    started = time.perf_counter()
    result = calculate_route(projection, "A", "D")
    service_duration = (time.perf_counter() - started) * 1000.0
    return result, service_duration, projection


def _routing_scenario(name: str, iterations: int, blocked_edges: set[str]) -> dict:
    topology = _topology()
    for _ in range(3):
        _route_sample(topology, blocked_edges=blocked_edges)
    samples = []
    route_id = None
    previous = None
    if name == "REROUTE":
        # Establish the same logical route context before measuring the blocked-edge reroute.
        initial_result, _, _ = _route_sample(topology, blocked_edges=set())
        previous = version_route(initial_result)
        route_id = previous.route_id
    for iteration in range(1, iterations + 1):
        result, service_duration, projection = _route_sample(topology, blocked_edges=blocked_edges)
        route = version_route(result, previous_route=previous, route_id=route_id)
        route_id = route.route_id
        previous = route
        samples.append({
            "scenario": name, "iteration": iteration, "route_status": result.status,
            "route_version": route.version, "calculation_duration_ms": result.calculation_duration_ms,
            "service_call_duration_ms": service_duration, "path_length": len(result.node_path),
            "edge_count": len(result.edge_path), "reroute": name == "REROUTE",
            "no_safe_route": result.no_safe_route,
        })
    primary = [sample["calculation_duration_ms"] for sample in samples]
    return {"scenario": name, "samples": samples, "summary": _summary(primary), "correctness": {"included_edge_ids": sorted(projection.included_edge_ids), "excluded_edge_ids": sorted(projection.excluded_edge_ids), "latest_route_version": previous.version if previous else None}}


def _summary(values: list[float]) -> dict:
    ordered = sorted(values)
    p95 = ordered[max(0, min(len(ordered) - 1, int((len(ordered) * .95) - 1)))]
    within = sum(value <= 1000 for value in values)
    return {"n": len(values), "median_ms": statistics.median(values), "p95_ms": p95, "max_ms": max(values), "within_1000ms": within, "exceeds_1000ms": len(values) - within, "metric_classification": "COMPUTE"}


def _response_breakdown() -> dict:
    paths = {}
    for name, blocked, acknowledge in (("normal_ack_path", False, True), ("ack_timeout_path", False, False), ("no_safe_route_path", True, True)):
        started = time.perf_counter()
        result = _run_scenario(name=name, blocked=blocked, acknowledge_normal=acknowledge)
        total = (time.perf_counter() - started) * 1000.0
        respond = result.get("respond_result", {})
        execution = respond.get("physical_execution") or {}
        paths[name] = {
            "status": result["status"], "routing_duration_ms": respond.get("routing_duration_ms"),
            "execution_duration_ms": execution.get("duration_ms"), "total_orchestration_duration_ms": total,
            "timing_classification": {"routing_duration_ms": "COMPUTE", "intentional_all_red_delay_ms": "INTENTIONAL_SAFETY_DELAY", "ack_wait_ms": "EXTERNAL_WAIT_SIMULATED", "total_orchestration_duration_ms": "TOTAL_ORCHESTRATION"},
            "note": "Mock ACK and isolated fixture timing; not ESP32 timing.",
        }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()
    if args.iterations <= 0:
        raise SystemExit("--iterations must be positive")
    topology = _topology()
    initial = _routing_scenario("INITIAL_SAFE_ROUTE", args.iterations, set())
    reroute = _routing_scenario("REROUTE", args.iterations, {"e2"})
    no_safe = _routing_scenario("NO_SAFE_ROUTE", args.iterations, {"e1", "e2", "e3", "e4"})
    response = _response_breakdown()
    report = {
        "report_type": "controlled software routing benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(), "iterations": args.iterations,
        "warm_up_iterations": 3, "routing_target_ms": 1000,
        "routing": {"INITIAL_SAFE_ROUTE": initial, "REROUTE": reroute, "NO_SAFE_ROUTE": no_safe},
        "response_breakdown": response,
        "statements": ["1000 ms ALL_RED transition is intentionally excluded from routing latency.", "500 ms ACK timeout is intentional and is reported as EXTERNAL_WAIT_SIMULATED.", "Mock ACK timings are not real ESP32 reliability/performance.", "Graph fixtures are controlled integration fixtures; production topology remains TBD_SOURCE."],
        "status": "PASS" if all(item["summary"]["exceeds_1000ms"] == 0 for item in (initial, reroute, no_safe)) else "FAIL",
        "remaining": ["real ESP32 timing: BLOCKED_EXTERNAL", "city-scale topology/load: TBD_SOURCE", "production graph scalability: TBD_SOURCE", "40-scenario fire verification: TBD_SOURCE"],
    }
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md = ["# Step 18 response timing", "", "Controlled software routing benchmark using deterministic graph fixtures and mock ACKs.", "", "## Routing"]
    for key, value in report["routing"].items():
        summary = value["summary"]
        md.append(f"- {key}: n={summary['n']}, median={summary['median_ms']:.3f} ms, p95={summary['p95_ms']:.3f} ms, max={summary['max_ms']:.3f} ms, within 1s={summary['within_1000ms']}, exceeds 1s={summary['exceeds_1000ms']}")
    md.extend(["", "## Response breakdown"])
    for key, value in response.items():
        md.append(f"- {key}: status={value['status']}, routing={value['routing_duration_ms']} ms, execution={value['execution_duration_ms']} ms, total={value['total_orchestration_duration_ms']:.3f} ms")
    md.extend(["", "The 1000 ms ALL_RED transition is intentional and excluded from routing latency. Mock ACK timings are not real ESP32 performance. Production topology remains TBD_SOURCE.", ""])
    MD_REPORT.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
