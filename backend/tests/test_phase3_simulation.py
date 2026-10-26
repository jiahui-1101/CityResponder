"""Cross-component safety and regression tests for the isolated Phase 3 runner."""

from datetime import timedelta
import hashlib
import sys

import pytest
from pydantic import ValidationError

from app.simulation.contracts import SimulatedEvidence
from app.simulation.evidence import SimulatedEvidenceValidator
from app.simulation.runner import BASE_TIME, Phase3SimulationRunner, SCENARIOS
from app.simulation.transport import SimulatedCommandTransport
from app.severity.policies import calculate_severity, evaluate_person_in_hazard
from app.vision.schemas import BoundingBox, Detection, PolygonPoint, PolygonROI
from scripts import run_phase3_simulation


def _item(evidence_id="one", *, source="MQ2", seconds=0, received=0, stale=False):
    return SimulatedEvidence(evidence_id=evidence_id, source_type=source, evidence_type="fixture", scenario_id="TEST", source_timestamp=BASE_TIME + timedelta(seconds=seconds), received_timestamp=BASE_TIME + timedelta(seconds=received), value=1, frame_or_message_id=evidence_id, freshness_status="STALE" if stale else "FRESH")


def test_evidence_contract_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        SimulatedEvidence.model_validate({**_item().model_dump(), "confidence": 2.0})


def test_evidence_contract_rejects_received_before_source():
    with pytest.raises(ValidationError):
        _item(seconds=2, received=1)


def test_evidence_contract_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        SimulatedEvidence.model_validate({"scenario_id": "TEST"})


def test_validator_rejects_duplicate_out_of_order_and_stale():
    evidence = [_item("new", seconds=2, received=2), _item("duplicate", seconds=2, received=2), _item("duplicate", seconds=2, received=2), _item("old", seconds=1, received=2), _item("stale", source="DHT22", seconds=-10, received=2, stale=True)]
    result = SimulatedEvidenceValidator().validate(evidence, now=BASE_TIME + timedelta(seconds=2))
    assert result.duplicate_ids == ["duplicate"]
    assert result.out_of_order_ids == ["old"]
    assert any(item["evidence_id"] == "stale" for item in result.rejected)


def test_transport_has_no_mqtt_capability():
    transport = SimulatedCommandTransport("TEST")
    assert transport.mqtt_capable is False
    assert transport.execute(None)["mqtt_publications"] == 0


def test_all_required_scenarios_pass_in_isolated_database(tmp_path):
    database = tmp_path / "phase3.db"
    runner = Phase3SimulationRunner(database)
    try:
        report = runner.run_all()
        assert report["summary"] == {"passed": 11, "failed": 0, "total": 11}
        assert {item["scenario_id"] for item in report["scenarios"]} == set(SCENARIOS)
        assert report["production_database_used"] is False
        assert report["mqtt_transport_available"] is False
        assert report["physical_actuation_available"] is False
        assert runner.verify_append_only() is True
    finally:
        runner.close()
    assert database.is_file()


def test_simulation_script_writes_only_to_new_output_directory(tmp_path, monkeypatch):
    project = __import__("pathlib").Path(__file__).resolve().parents[2]
    geometry_path = project / "frontend" / "src" / "data" / "routeGeometry.json"
    report_path = project / "frontend" / "src" / "data" / "phase3SimulationResults.json"
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (geometry_path, report_path)
    }
    output = tmp_path / "new-run"
    monkeypatch.setattr(sys, "argv", ["run_phase3_simulation", "--output-dir", str(output)])

    assert run_phase3_simulation.main() == 0
    assert (output / "simulation_audit.db").is_file()
    assert (output / "simulation_results.json").is_file()
    assert (output / "routeGeometry.json").is_file()
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (geometry_path, report_path)
    }


def test_simulation_script_refuses_existing_output_directory(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    preserved = output / "keep.txt"
    preserved.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_phase3_simulation", "--output-dir", str(output)])

    with pytest.raises(FileExistsError):
        run_phase3_simulation.main()
    assert preserved.read_text(encoding="utf-8") == "preserve"


def test_routes_use_only_confirmed_draft_graph_ids(tmp_path):
    runner = Phase3SimulationRunner(tmp_path / "routes.db")
    try: report = runner.run_all()
    finally: runner.close()
    for scenario in report["scenarios"]:
        plan = scenario.get("response_plan")
        if not plan: continue
        for route_name in ("selected_route", "alternative_route"):
            route = plan.get(route_name)
            if route:
                assert set(route["edge_path"]) <= {"PE02", "PE04", "PE06", "PE07"}
                assert set(route["node_path"]) <= {"N2", "N4", "N5", "N6", "N7"}
                assert route["cost_unit"] == "draft_pixel_proxy × risk multiplier"


def _run(tmp_path, key):
    runner = Phase3SimulationRunner(tmp_path / f"{key}.db")
    try: return runner.run_scenario(key, SCENARIOS[key])
    finally: runner.close()


def test_person_hazard_escalates_deterministic_positive_fixture(tmp_path):
    result = _run(tmp_path, "D")
    assert result.actual["person_in_hazard"] is True
    assert result.actual["severity"] == "CRITICAL"


def test_blocked_primary_selects_standby_route(tmp_path):
    assert _run(tmp_path, "C").actual["selected_route"] == ["PE02", "PE07"]


def test_both_routes_blocked_returns_no_safe_route(tmp_path):
    assert _run(tmp_path, "G").actual["no_safe_route"] is True


def test_ack_timeout_retries_once_and_applies_simulated_failsafe(tmp_path):
    execution = _run(tmp_path, "H").response_plan.execution
    assert execution["status"] == "FAILED_IN_SIMULATION"
    assert execution["retry_limit"] == 1
    assert execution["failsafe"] == "SAFE_DEFAULT_APPLIED_IN_SIMULATION"
    assert execution["mqtt_publications"] == 0
    assert execution["lifecycle"]["status"] == "SAFE_DEFAULT"


def test_confirmed_lifecycle_reaches_verified_fire(tmp_path):
    lifecycle = _run(tmp_path, "B").response_plan.execution["lifecycle"]
    assert lifecycle["transitions"] == ["RESPONDING", "EN_ROUTE", "ARRIVED", "RESOLVED", "VERIFIED_FIRE"]


def test_semantic_replay_is_deterministic(tmp_path):
    outputs=[]
    for index in range(2):
        runner=Phase3SimulationRunner(tmp_path/f"replay-{index}.db")
        try:
            result=runner.run_scenario("K",SCENARIOS["K"])
            outputs.append({key:result.actual[key] for key in ("incident_confirmed","severity","selected_route","execution_status")})
        finally: runner.close()
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    ("mq2", "temperature", "fire_box", "expected"),
    [
        (500, 30, (30, 30, 30, 30), "LOW"),
        (1250, 35, (10, 10, 60, 60), "MEDIUM"),
        (2000, 40, (10, 10, 80, 80), "HIGH"),
        (2000, 40, (0, 0, 100, 100), "CRITICAL"),
    ],
)
def test_actual_severity_policy_bands(mq2, temperature, fire_box, expected):
    zone = PolygonROI(name="deterministic", points=[PolygonPoint(x=0,y=0),PolygonPoint(x=100,y=0),PolygonPoint(x=100,y=100),PolygonPoint(x=0,y=100)])
    detection = Detection(class_name="fire", confidence=.9, bounding_box=BoundingBox(x1=fire_box[0],y1=fire_box[1],x2=fire_box[2],y2=fire_box[3]))
    result = calculate_severity(mq2_reading=mq2, dht22_reading=temperature, detections=[detection], building_roi=zone, hazard_zone=zone, zone_label="normal-risk")
    assert result.severity_label == expected


def test_actual_person_geometry_boundary_confidence_and_multiple_people():
    zone = PolygonROI(name="deterministic", points=[PolygonPoint(x=20,y=20),PolygonPoint(x=80,y=20),PolygonPoint(x=80,y=80),PolygonPoint(x=20,y=80)])
    outside = Detection(class_name="person", confidence=.99, bounding_box=BoundingBox(x1=85,y1=85,x2=95,y2=95))
    low = Detection(class_name="person", confidence=.49, bounding_box=BoundingBox(x1=40,y1=40,x2=60,y2=60))
    boundary = Detection(class_name="person", confidence=.5, bounding_box=BoundingBox(x1=10,y1=10,x2=30,y2=30))
    assert evaluate_person_in_hazard([outside], zone) is False
    assert evaluate_person_in_hazard([low], zone) is False
    assert evaluate_person_in_hazard([outside, boundary], zone) is True
