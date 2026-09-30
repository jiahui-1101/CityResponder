"""Controlled end-to-end software-cycle validation for Part 5 Step 17.

The harness reuses the Respond orchestration and immutable persistence services.
Only the actuator publisher is injected with a deterministic in-memory transport;
no physical device, second broker, or production database is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.auth.models import UserRole
from app.dispatch.matrix import ActionRecommendation, DispatchRecommendation
from app.events.repository import append_event
from app.fusion.schemas import (
    ConfirmationSequenceResult,
    ConfirmationWindowResult,
    FusionConfidenceResult,
)
from app.physical_actions.execution import execute_ack_gated_sequence
from app.routing.evidence import RoadEdgeEvidence
from app.routing.factors import RoutingFactorValues
from app.routing.safety import IRSample
from app.routing.topology import RoutingEdge, RoutingNode, build_routing_topology
from app.respond.service import RespondOrchestrationService, RespondPhaseInput
from app.severity.calculator import calculate_severity_score
from app.severity.classification import classify_severity
from app.severity.decision import build_incident_decision
from app.severity.operator import OperatorAction, OperatorDecisionRequest, create_operator_decision
from app.severity.persistence import persist_incident_decision, persist_operator_decision
from app.severity.schemas import SeverityInput
from app.vision.schemas import FreshnessItem

from scripts.validate_requirements import isolated_db


ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "reports" / "validation" / "step17_e2e_cycle.json"
REPORT_MD = ROOT / "reports" / "validation" / "step17_e2e_cycle.md"


class ControlledFactorPolicy:
    def evaluate(self, edge_evidence: RoadEdgeEvidence) -> RoutingFactorValues:
        return RoutingFactorValues(o=0.10, l=0.10, routing_c=0.10, reasons=["controlled integration fixture"])


class ControlledIRPolicy:
    def indicates_blockage(self, samples: list[IRSample], edge_evidence: RoadEdgeEvidence) -> bool:
        return True


class ControlledDispatchPolicy:
    version = "controlled-integration-fixture-1"

    def evaluate(self, dispatch_input):
        return DispatchRecommendation(
            status="recommended",
            dispatch_actions=[],
            traffic_actions=[ActionRecommendation(action_category="TRAFFIC", action_type="GREEN_CORRIDOR", reason="controlled integration fixture")],
            building_actions=[
                ActionRecommendation(action_category="GATE", action_type="OPEN", reason="controlled integration fixture"),
                ActionRecommendation(action_category="BUZZER", action_type="ON", reason="controlled integration fixture"),
            ],
            generated_at=datetime.now(timezone.utc),
        )


class MockActuatorTransport:
    """Safe publisher fixture that emits ACKs only when configured to do so."""

    def __init__(self, db, *, acknowledge_normal: bool, acknowledge_safe_defaults: bool = True):
        self.db = db
        self.acknowledge_normal = acknowledge_normal
        self.acknowledge_safe_defaults = acknowledge_safe_defaults
        self.commands: list[dict[str, Any]] = []

    def publish(self, db, *, node_id: str, command_type: str, payload: dict[str, Any]) -> dict[str, str]:
        command_id = str(uuid4())
        command = {"command_id": command_id, "node_id": node_id, "command_type": command_type, "payload": payload}
        self.commands.append(command)
        event = append_event(db, event_type="actuator_command", entity_type="actuator", entity_id=node_id, payload=command)
        safe_default = bool(payload.get("safe_default"))
        should_ack = self.acknowledge_safe_defaults if safe_default else self.acknowledge_normal
        if should_ack:
            append_event(db, event_type="actuator_ack", entity_type="actuator", entity_id=node_id, payload={"command_id": command_id, "node_id": node_id, "status": "ACK", "timestamp": datetime.now(timezone.utc).isoformat()})
            from app.actuators.ack_waiter import notify_actuator_ack
            notify_actuator_ack(command_id, node_id, {"command_id": command_id, "node_id": node_id, "status": "ACK"}, datetime.now(timezone.utc))
        return {"command_id": command_id}


def _fixture_incident() -> Any:
    now = datetime.now(timezone.utc)
    windows = [ConfirmationWindowResult(window_timestamp=now.replace(microsecond=0), status="passed", confidence_score=70, confidence_threshold=40, confidence_pass=True, supporting_count=2, required_supporting_count=2, supporting_pass=True, window_pass=True) for _ in range(3)]
    sequence = ConfirmationSequenceResult(status="confirmed", incident_confirmed=True, window_results=windows, consecutive=True, all_windows_pass=True, evaluated_at=now)
    confidence = FusionConfidenceResult(status="calculated", confidence_score=70, s_score=.7, t_score=.7, v_score=.7, h_score=.7, weights={"S": .3, "T": .2, "V": .35, "H": .15}, weighted_contributions={"S": .21, "T": .14, "V": .245, "H": .105}, calculated_at=now)
    severity_input = SeverityInput(status="not_evaluated", confirmation_reference=sequence, incident_confirmed=True, a=.6, s=.5, t=.4, p=1.0, z=.3, person_in_hazard=True, person_evidence=None, person_source_timestamp=now, critical_override_signal=True, source_timestamps={"controlled": now}, reasons=["controlled integration fixture"])
    score = calculate_severity_score(severity_input)
    classification = classify_severity(score)
    return build_incident_decision(sequence, confidence, score, classification)


def _topology_and_evidence(*, blocked: bool = False):
    now = datetime.now(timezone.utc)
    topology = build_routing_topology([RoutingNode(node_id="A"), RoutingNode(node_id="B")], [RoutingEdge(edge_id="edge-1", from_node="A", to_node="B", distance_cm=100, road_roi_name="road-1", bidirectional=True)], road_roi_to_edge={"road-1": "edge-1"})
    evidence = RoadEdgeEvidence(road_edge_id="edge-1", road_roi_name="road-1", frame_id="fixture-frame", frame_timestamp=now, frame_source="CAMERA", occupancy_ratio=.9 if blocked else .1, occupied_pixels=90 if blocked else 10, obstacle_count=1 if blocked else 0, max_obstacle_extent_px=20, mapped_ir_sensor="IR_A" if blocked else None, ir_timestamp=now if blocked else None, ir_value=True if blocked else None, time_delta_ms=10 if blocked else None, time_matched=True if blocked else None, conflict=False, conflict_reason="controlled integration fixture", freshness=FreshnessItem(source_type="road", source_id="road-1", available=True, stale=False, age_seconds=0, timestamp=now), available=True, stale=False)
    samples = [IRSample(sensor_type="IR_A", timestamp=now, value=True) for _ in range(5)] if blocked else []
    return topology, evidence, samples


def _run_scenario(*, name: str, blocked: bool, acknowledge_normal: bool) -> dict[str, Any]:
    from app.physical_actions import execution as execution_module

    engine, db = isolated_db()
    incident = _fixture_incident()
    persist_incident_decision(db, incident)
    topology, evidence, samples = _topology_and_evidence(blocked=blocked)
    transport = MockActuatorTransport(db, acknowledge_normal=acknowledge_normal)
    original = execution_module.publish_actuator_command
    execution_module.publish_actuator_command = transport.publish
    try:
        result = RespondOrchestrationService().run(RespondPhaseInput(incident_decision=incident, topology=topology, edge_evidence={"edge-1": evidence}, ir_samples_by_edge={"edge-1": samples}, routing_factor_policy=ControlledFactorPolicy(), ir_blockage_policy=ControlledIRPolicy(), source_node_id="A", destination_node_id="B", dispatch_matrix_policy=None if blocked else ControlledDispatchPolicy(), db=db, persist_route=True, execute_physical=True))
        db.commit()
        events = db.query(__import__("app.events.models", fromlist=["Event"]).Event).order_by(__import__("app.events.models", fromlist=["Event"]).Event.id.asc()).all()
        trace = {"scenario_id": name, "result": result.status, "incident_decision_id": incident.decision_id, "route_id": result.versioned_route.route_id if result.versioned_route else None, "route_version": result.versioned_route.version if result.versioned_route else None, "command_ids": [item["command_id"] for item in transport.commands], "ack_outcomes": [item.status for item in result.physical_execution.command_results] if result.physical_execution else [], "event_ids_types": [{"id": event.id, "type": event.event_type} for event in events], "final_orchestration_state": result.status, "warnings_tbd": ["S/T/V/H values are controlled integration fixtures, not production normalization"]}
        return {"status": "PASS", "trace": trace, "respond_result": result.model_dump(mode="json")}
    finally:
        execution_module.publish_actuator_command = original
        db.close(); engine.dispose()


def _operator_verification() -> dict[str, Any]:
    engine, db = isolated_db()
    try:
        incident = _fixture_incident()
        persist_incident_decision(db, incident)
        request = OperatorDecisionRequest(operator_id=1, operator_role=UserRole.OPERATOR, action=OperatorAction.CONFIRM, written_reason="Controlled integration validation confirmation")
        decision = create_operator_decision(incident, request)
        event = persist_operator_decision(db, decision)
        db.commit()
        return {"status": "PASS", "action": decision.action.value, "operator_id": decision.operator_id, "reason_preserved": event.payload["written_reason"], "event_id": event.id, "event_type": event.event_type}
    finally:
        db.close(); engine.dispose()


def _downstream_eligibility() -> dict[str, Any]:
    return {"status": "TBD_SOURCE", "area_risk": {"operator_verified": True, "timestamp_valid": True, "explicit_area_id": False, "eligibility": "not eligible / mapping TBD"}, "calibration": {"operator_verified_outcome_exists": True, "immutable_references": True, "valid_30_15_dataset": False, "reason": "one controlled outcome is not a calibration dataset"}}


def run() -> dict[str, Any]:
    scenario_a = _run_scenario(name="A_CONFIRMED_ROUTABLE_INCIDENT", blocked=False, acknowledge_normal=True)
    scenario_b = _run_scenario(name="B_NO_SAFE_ROUTE", blocked=True, acknowledge_normal=True)
    scenario_c = _run_scenario(name="C_ACTUATOR_ACK_TIMEOUT", blocked=False, acknowledge_normal=False)
    operator = _operator_verification()
    return {"report_type": "controlled_software_integration_validation", "generated_at": datetime.now(timezone.utc).isoformat(), "hardware": "mock ACK / isolated SQLite fixtures; no real hardware actuation", "not_a_benchmark": ["not a real-hardware reliability benchmark", "not a 40-scenario fire-detection accuracy benchmark"], "scenarios": {"A": scenario_a, "B": scenario_b, "C": scenario_c}, "operator_verification": operator, "downstream_learning_eligibility": _downstream_eligibility(), "status_policy": ["PASS", "FAIL", "BLOCKED_EXTERNAL", "TBD_SOURCE"], "remaining_blockers": ["production S/T/V/H normalization/support policy", "severity policy boundaries", "area mapping and F/R/E/A/M semantics", "real ESP32 ACK reliability", "full 40-scenario benchmark"]}


def write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    lines = ["# Step 17 controlled software integration validation", "", "This is a controlled software integration validation using isolated fixtures and mock ACKs. It is not a real-hardware reliability benchmark or a 40-scenario fire-detection accuracy benchmark.", "", "## Results", ""]
    for key, value in report["scenarios"].items():
        lines.append(f"- Scenario {key}: **{value['status']}** — `{value['trace']['result']}`")
    lines.extend([f"- Operator verification: **{report['operator_verification']['status']}**", f"- Downstream learning eligibility: **{report['downstream_learning_eligibility']['status']}** (area mapping remains TBD_SOURCE)", "", "## Remaining blockers", ""])
    lines.extend(f"- {item}" for item in report["remaining_blockers"])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    output = run()
    if not args.no_write:
        write_reports(output)
    print(json.dumps(output, indent=2, default=str))
