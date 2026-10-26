"""Phase 3.5 routing oracle, image geometry and shadow-mode regression tests."""

from datetime import datetime, timezone
from pathlib import Path

import cv2
import networkx as nx
import pytest

from app.routing.graph import ActiveRoutingGraphProjection
from app.routing.route import calculate_route
from app.routing.versioning import version_route
from app.simulation.route_visualization import load_route_image_geometry, map_route_to_image
from app.vision.shadow import evaluate_live_shadow


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "reports" / "debug" / "camera_alignment" / "road_graph_phase_b1_final_review_draft.json"
IMAGE = ROOT / "reports" / "debug" / "camera_alignment" / "camera_alignment_20261025T084211_819245Z_index0_raw.jpg"


def _projection(edges):
    graph = nx.MultiDiGraph()
    graph.add_nodes_from({node for edge in edges for node in edge[:2]})
    for source, destination, edge_id, cost in edges:
        graph.add_edge(source, destination, key=edge_id, edge_id=edge_id, edge_cost=float(cost), distance_cm=float(cost))
    return ActiveRoutingGraphProjection(graph=graph, included_edge_ids=[edge[2] for edge in edges], generated_at=datetime.now(timezone.utc))


@pytest.mark.parametrize("edges,source,destination", [
    ([("N2","N4","PE04",10),("N4","N5","PE06",10),("N2","N6","PE02",12),("N6","N5","X",12)], "N2", "N5"),
    ([("A","B","AB",2),("B","D","BD",3),("A","C","AC",1),("C","D","CD",9)], "A", "D"),
    ([("A","B","AB",1),("B","D","BD",1),("A","C","AC",1),("C","D","CD",1)], "A", "D"),
])
def test_astar_matches_independent_dijkstra_oracle(edges, source, destination):
    projection = _projection(edges)
    actual = calculate_route(projection, source, destination)
    oracle = nx.dijkstra_path(projection.graph, source, destination, weight="edge_cost")
    oracle_cost = nx.dijkstra_path_length(projection.graph, source, destination, weight="edge_cost")
    assert actual.status == "route_found"
    assert actual.node_path == oracle
    assert actual.total_edge_cost == pytest.approx(oracle_cost)
    assert actual.total_edge_cost == pytest.approx(sum(projection.graph[u][v][edge]["edge_cost"] for u, v, edge in zip(actual.node_path, actual.node_path[1:], actual.edge_path)))


def test_astar_no_path_invalid_nodes_and_same_node_fail_safely():
    projection = _projection([("A","B","AB",1), ("C","D","CD",1)])
    assert calculate_route(projection,"A","D").status == "NO_SAFE_ROUTE"
    assert calculate_route(projection,"missing","D").status == "invalid_configuration"
    assert calculate_route(projection,"A","A").status == "invalid_configuration"
    allowed = calculate_route(projection,"A","A",allow_same_node=True)
    assert allowed.status == "route_found" and allowed.edge_path == [] and allowed.total_edge_cost == 0


def test_equal_cost_tie_is_deterministic_across_edge_input_order():
    edges=[("A","B","AB",1),("B","D","BD",1),("A","C","AC",1),("C","D","CD",1)]
    forward=calculate_route(_projection(edges),"A","D")
    reverse=calculate_route(_projection(list(reversed(edges))),"A","D")
    assert forward.node_path == reverse.node_path == ["A","B","D"]
    assert forward.edge_path == reverse.edge_path == ["AB","BD"]


def test_malformed_nonpositive_or_nonfinite_costs_are_not_routed():
    projection=_projection([("A","B","zero",0),("B","C","nan",float("nan"))])
    assert calculate_route(projection,"A","C").status == "NO_SAFE_ROUTE"


def test_route_version_changes_and_clears_stale_path():
    first = calculate_route(_projection([("A","B","AB",1), ("B","D","BD",1)]),"A","D")
    v1 = version_route(first, route_id="phase35-test")
    blocked = calculate_route(_projection([("A","B","AB",1), ("C","D","CD",1)]),"A","D")
    v2 = version_route(blocked, previous_route=v1)
    assert v2.version == 2 and v2.invalidates_prior_commands is True
    assert v2.no_safe_route is True and v2.node_path == [] and v2.edge_path == []


def test_documented_geometry_maps_actual_route_continuously():
    geometry = load_route_image_geometry(GRAPH,image_asset="/assets/test.jpg")
    overlay = map_route_to_image(geometry,["N2","N4","N5"],["PE04","PE06"])
    assert overlay.continuous is True and not overlay.missing_edge_ids
    assert overlay.origin == geometry.nodes["N2"].position
    assert overlay.destination == geometry.nodes["N5"].position
    assert all(0 <= point.normalized_x <= 1 and 0 <= point.normalized_y <= 1 for point in overlay.selected_points)
    assert geometry.image_geometry_version.startswith("raw-camera-1920x1080:")


def test_geometry_never_invents_unknown_edge_and_validates_sequence():
    geometry = load_route_image_geometry(GRAPH,image_asset="/assets/test.jpg")
    overlay = map_route_to_image(geometry,["N2","N4"],["UNKNOWN"])
    assert overlay.selected_points == [] and overlay.missing_edge_ids == ["UNKNOWN"] and overlay.continuous is False
    with pytest.raises(ValueError): map_route_to_image(geometry,["N2","N6"],["PE04"])


def test_reference_image_matches_geometry_dimensions():
    image = cv2.imread(str(IMAGE))
    assert image is not None and image.shape[:2] == (1080,1920)


def test_live_shadow_preserves_provenance_and_has_no_side_effect_capability():
    now = datetime.now(timezone.utc)
    result = evaluate_live_shadow(frame_id="frame-7",timestamp=now,processed_at=now,crop_geometry_version="crop-v1",detections=[{"class_name":"FIRE","confidence":.9}],segmentations=[{"class_name":"ROAD_OBSTACLE","confidence":.8}])
    assert result.status == "OBSERVATIONS_PRESENT" and result.source_frame_id == "frame-7"
    assert result.mapped_edge_ids == []
    assert not any((result.incident_created,result.route_recalculated,result.mqtt_published,result.hardware_actuated))
