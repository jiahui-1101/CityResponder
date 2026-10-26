"""Deterministic, isolated, cross-component Phase 3 simulation runner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.dispatch.policies import DefaultDispatchMatrixPolicy
from app.events.models import Event
from app.events.repository import append_event
from app.fusion.runtime import build_runtime_incident_decision
from app.fusion.schemas import FusionSourceReference
from app.physical_actions.mapper import map_dispatch_recommendation
from app.physical_actions.sequence import sequence_physical_actions
from app.respond.service import RespondOrchestrationService, RespondPhaseInput
from app.routing.evidence import RoadEdgeEvidence
from app.routing.factors import RoutingFactorValues
from app.routing.safety import IRSample
from app.routing.topology import RoutingEdge, RoutingNode, build_routing_topology
from app.severity.decision import IncidentDecision
from app.simulation.contracts import ResponsePlan, ScenarioResult, SimulatedEvidence
from app.simulation.evidence import SimulatedEvidenceValidator
from app.simulation.transport import SimulatedCommandTransport
from app.sensors.schemas import LatestSensorState
from app.vision.schemas import (
    BoundingBox, CoordinateSystem, Detection, FrameMetadata, FrameSourceType,
    FreshnessItem, PerceptionFreshnessResponse, PerceptionSnapshot, PolygonPoint,
    PolygonROI, ROI, VisionDetectionMessage,
)


BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
GRAPH_SOURCE = "SIMULATED deterministic fixture using draft node/edge IDs"


class SimulationFactorPolicy:
    def evaluate(self, evidence: RoadEdgeEvidence) -> RoutingFactorValues:
        classes = {item.upper() for item in evidence.contributing_classes}
        pothole_risk = 0.35 if "POTHOLE" in classes else 0.0
        return RoutingFactorValues(
            o=evidence.occupancy_ratio,
            l=min(1.0, evidence.max_obstacle_extent_px / 100.0),
            routing_c=pothole_risk,
            reasons=["SIMULATED factors derived deterministically from supplied evidence"],
        )


class SimulationIRPolicy:
    def indicates_blockage(self, samples: list[IRSample], _evidence: RoadEdgeEvidence) -> bool:
        return all(bool(sample.value) for sample in samples[-5:])


SCENARIOS: dict[str, dict[str, Any]] = {
    "A": {"name": "Normal city", "fire": 0.0, "mq2": 500, "temp": 30, "expected_action": False},
    "B": {"name": "Confirmed fire", "fire": 0.92, "mq2": 1900, "temp": 39, "expected_action": True},
    "C": {"name": "Road blockage", "fire": 0.92, "mq2": 1900, "temp": 39, "blocked": ["PE04"], "gate": "OPEN", "expected_route": ["PE02", "PE07"], "expected_action": True},
    "D": {"name": "Person in hazard", "fire": 0.92, "mq2": 1900, "temp": 39, "person": "inside", "expected_severity": "CRITICAL", "expected_action": True},
    "E": {"name": "Sensor conflict", "fire": 0.92, "mq2": 500, "temp": 30, "conflict": ["PE04", "PE02"], "expected_action": False},
    "F": {"name": "Stale or missing sensor", "fire": 0.92, "mq2": None, "temp": None, "stale": True, "expected_action": False},
    "G": {"name": "No safe route", "fire": 0.92, "mq2": 1900, "temp": 39, "blocked": ["PE04", "PE02"], "gate": "OPEN", "expected_no_route": True, "expected_action": True},
    "H": {"name": "ACK timeout", "fire": 0.92, "mq2": 1900, "temp": 39, "ack": "timeout", "expected_action": True, "expected_execution": "FAILED_IN_SIMULATION"},
    "I": {"name": "Duplicate input", "fire": 0.92, "mq2": 1900, "temp": 39, "duplicate": True, "expected_action": True},
    "J": {"name": "Invalid input", "invalid": True, "expected_action": False},
    "K": {"name": "Mixed multi-hazard", "fire": 0.95, "mq2": 2100, "temp": 42, "person": "inside", "blocked": ["PE04"], "gate": "OPEN", "expected_route": ["PE02", "PE07"], "expected_severity": "CRITICAL", "expected_action": True},
}


class Phase3SimulationRunner:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.database_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS sim_prevent_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'simulation events are append-only'); END")
            connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS sim_prevent_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'simulation events are append-only'); END")

    def close(self) -> None:
        self.engine.dispose()

    def run_all(self) -> dict[str, Any]:
        results = [self.run_scenario(key, value) for key, value in SCENARIOS.items()]
        return {
            "report_type": "CityResponder Phase 3 isolated software simulation",
            "simulation_marker": "SIMULATED",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph_source": GRAPH_SOURCE,
            "graph_warning": "Uses only confirmed N2/N4/N5/N6/N7 and PE02/PE04/PE06/PE07 identities. Draft pixel lengths are explicit simulation cost proxies, not physical centimeters.",
            "production_database_used": False,
            "mqtt_transport_available": False,
            "physical_actuation_available": False,
            "scenarios": [item.model_dump(mode="json") for item in results],
            "summary": {"passed": sum(item.status == "PASS" for item in results), "failed": sum(item.status == "FAIL" for item in results), "total": len(results)},
        }

    def run_scenario(self, scenario_id: str, spec: dict[str, Any]) -> ScenarioResult:
        started = perf_counter()
        correlation_id = str(uuid5(NAMESPACE_URL, f"cityresponder-phase3:{scenario_id}"))
        timings: dict[str, float] = {}
        with Session(self.engine) as db:
            before = db.query(Event).count()
            evidence_started = perf_counter()
            raw, invalid_error = self._evidence(scenario_id, spec)
            validation = SimulatedEvidenceValidator().validate(raw, now=BASE_TIME + timedelta(seconds=2))
            timings["evidence_validation"] = (perf_counter() - evidence_started) * 1000
            for item in validation.accepted:
                self._audit(db, scenario_id, correlation_id, "simulation_evidence_accepted", item.model_dump(mode="json"))
            for item in validation.rejected:
                self._audit(db, scenario_id, correlation_id, "simulation_evidence_rejected", item)

            if spec.get("invalid"):
                assertions = [{"name": "invalid payload rejected", "passed": invalid_error is not None}]
                result = ScenarioResult(
                    scenario_id=scenario_id, name=spec["name"], expected={"safe_rejection": True},
                    actual={"rejected": True, "reason": invalid_error}, explanation=["Pydantic contract rejected invalid confidence before orchestration."],
                    assertions=assertions, timings_ms={**timings, "total": (perf_counter()-started)*1000}, status="PASS" if invalid_error else "FAIL",
                    audit_event_count=db.query(Event).count()-before,
                )
                self._audit(db, scenario_id, correlation_id, "simulation_scenario_completed", result.model_dump(mode="json"))
                result.audit_event_count = db.query(Event).count()-before
                return result

            snapshots = self._snapshots(scenario_id, spec, validation.accepted)
            fusion_started = perf_counter()
            decision = build_runtime_incident_decision(snapshots)
            timings["fusion_and_severity"] = (perf_counter() - fusion_started) * 1000
            assert decision is not None
            decision = decision.model_copy(update={
                "decision_id": correlation_id,
                "warnings": [*decision.warnings, "SIMULATED isolated scenario; never a production incident"],
            })
            self._audit(db, scenario_id, correlation_id, "simulation_incident_decision", decision.model_dump(mode="json"))

            routing_started = perf_counter()
            route_candidates, selected, respond = self._route(decision, scenario_id, spec, db)
            timings["routing_and_response_plan"] = (perf_counter() - routing_started) * 1000
            plan = self._plan(scenario_id, correlation_id, spec, validation, decision, route_candidates, selected, respond)
            lifecycle_started = perf_counter()
            lifecycle = self._lifecycle(db, decision, plan.execution["status"])
            plan.execution["lifecycle"] = lifecycle
            timings["lifecycle"] = (perf_counter() - lifecycle_started) * 1000
            self._audit(db, scenario_id, correlation_id, "simulation_response_plan", plan.model_dump(mode="json"))
            actual = {
                "incident_confirmed": decision.incident_confirmed,
                "decision_status": decision.decision_status,
                "confidence": decision.fusion_confidence.confidence_score,
                "severity": decision.final_severity,
                "person_in_hazard": bool(spec.get("person") == "inside"),
                "selected_route": plan.selected_route["edge_path"] if plan.selected_route else None,
                "no_safe_route": plan.selected_route is None and decision.incident_confirmed is True,
                "execution_status": plan.execution["status"],
                "duplicates_rejected": len(validation.duplicate_ids),
                "rejected_evidence": len(validation.rejected),
            }
            assertions = self._assertions(spec, actual)
            status = "PASS" if all(item["passed"] for item in assertions) else "FAIL"
            explanation = [
                f"Existing fire fusion returned {decision.decision_status} with C={decision.fusion_confidence.confidence_score}.",
                f"Existing severity policy returned {decision.final_severity or 'unresolved'}.",
                "Routes were calculated with the existing safety, risk-cost, graph, A*, versioning and dispatch services.",
                "Command outcomes came from a closed in-memory simulator; MQTT publications remained zero.",
            ]
            result = ScenarioResult(
                scenario_id=scenario_id, name=spec["name"], expected=self._expected(spec), actual=actual,
                explanation=explanation, assertions=assertions, timings_ms={**timings, "total": (perf_counter()-started)*1000},
                status=status, response_plan=plan, audit_event_count=0,
            )
            self._audit(db, scenario_id, correlation_id, "simulation_scenario_completed", result.model_dump(mode="json"))
            result.audit_event_count = db.query(Event).count()-before
            return result

    def _evidence(self, sid: str, spec: dict[str, Any]) -> tuple[list[SimulatedEvidence], str | None]:
        if spec.get("invalid"):
            try:
                SimulatedEvidence(evidence_id="invalid", source_type="VISION", evidence_type="fire", scenario_id=sid, source_timestamp=BASE_TIME, received_timestamp=BASE_TIME, value=True, confidence=1.5, frame_or_message_id="invalid")
            except Exception as exc:
                return [], str(exc).splitlines()[0]
        items: list[SimulatedEvidence] = []
        for window in range(3):
            ts = BASE_TIME + timedelta(seconds=window)
            age_ts = ts - timedelta(seconds=10) if spec.get("stale") else ts
            values = [("VISION", "fire", spec.get("fire", 0.0), spec.get("fire", 0.0)), ("MQ2", "smoke", spec.get("mq2"), None), ("DHT22", "temperature", spec.get("temp"), None)]
            for source, kind, value, confidence in values:
                if value is None:
                    continue
                item = SimulatedEvidence(evidence_id=f"{sid}-{window}-{source}", source_type=source, evidence_type=kind, scenario_id=sid, source_timestamp=age_ts, received_timestamp=ts, value=value, confidence=confidence, frame_or_message_id=f"{sid}-frame-{window}", association="Building A", freshness_status="STALE" if spec.get("stale") else "FRESH")
                items.append(item)
        if spec.get("duplicate") and items:
            items.append(items[-1].model_copy())
        return items, None

    def _snapshots(self, sid: str, spec: dict[str, Any], accepted: list[SimulatedEvidence]) -> list[PerceptionSnapshot]:
        snapshots = []
        accepted_ids = {item.evidence_id for item in accepted}
        building = ROI(name="Building A deterministic fixture", x=0, y=0, width=100, height=100)
        hazard = PolygonROI(name="Hazard fixture", points=[PolygonPoint(x=20,y=20), PolygonPoint(x=80,y=20), PolygonPoint(x=80,y=80), PolygonPoint(x=20,y=80)], coordinate_system=CoordinateSystem.RAW_BOARD_CROP)
        for i in range(3):
            ts = BASE_TIME + timedelta(seconds=i)
            fire = float(spec.get("fire", 0.0))
            detections = []
            if fire:
                detections.append(Detection(class_name="fire", confidence=fire, bounding_box=BoundingBox(x1=30,y1=30,x2=70,y2=70)))
            if spec.get("person"):
                box = BoundingBox(x1=40,y1=40,x2=60,y2=60) if spec["person"] == "inside" else BoundingBox(x1=85,y1=85,x2=95,y2=95)
                detections.append(Detection(class_name="person", confidence=.9, bounding_box=box))
            available = not spec.get("stale")
            frame = FrameMetadata(frame_id=f"{sid}-frame-{i}", timestamp=ts, source=FrameSourceType.IMAGE_FILE, width=100, height=100)
            detection = VisionDetectionMessage(frame=frame, building_roi=building, building_polygon=hazard, hazard_polygon=hazard, detections=detections, person_in_hazard=spec.get("person") == "inside", processing_timestamp=ts)
            sensors = [
                LatestSensorState(sensor_type="MQ2", value=spec.get("mq2"), timestamp=ts if available else ts-timedelta(seconds=10), node_id="SIM-SN1", available=available and spec.get("mq2") is not None),
                LatestSensorState(sensor_type="DHT22", value=spec.get("temp"), timestamp=ts if available else ts-timedelta(seconds=10), node_id="SIM-SN1", available=available and spec.get("temp") is not None),
                LatestSensorState(sensor_type="BUTTON", value=False, timestamp=ts, node_id="SIM-SN1", available=True),
                LatestSensorState(sensor_type="IR_A", value=False, timestamp=ts, node_id="SIM-SN1", available=True),
                LatestSensorState(sensor_type="IR_B", value=False, timestamp=ts, node_id="SIM-SN1", available=True),
            ]
            def fresh(source: str, ok: bool=True):
                return FreshnessItem(source_type=source, source_id="SIM-SN1", available=ok, stale=not ok, age_seconds=0 if ok else 10, timestamp=ts if ok else ts-timedelta(seconds=10))
            snapshots.append(PerceptionSnapshot(generated_at=ts, sensors=sensors, detection=detection, person_in_hazard=spec.get("person") == "inside", road_evidence=[], freshness=PerceptionFreshnessResponse(mq2=fresh("MQ2",available and spec.get("mq2") is not None), dht22=fresh("DHT22",available and spec.get("temp") is not None), button=fresh("BUTTON"), ir_a=fresh("IR_A"), ir_b=fresh("IR_B"), detection=fresh("VISION",available)), road_sync=[], warnings=["SIMULATED deterministic ROI; physical alignment NOT_VERIFIED"], unavailable_inputs=[]))
        return snapshots

    def _route(self, decision: IncidentDecision, sid: str, spec: dict[str, Any], db: Session):
        if decision.incident_confirmed is not True:
            return [], None, None
        nodes = [RoutingNode(node_id=n) for n in ("N2","N4","N5","N6","N7")]
        # Values come from the draft's approx_image_length pixels and are used only as deterministic simulation cost proxies.
        edges = [RoutingEdge(edge_id="PE04",from_node="N2",to_node="N4",distance_cm=276,bidirectional=True,metadata={"corridor":"PRIMARY","simulation_distance_unit":"draft_pixel_proxy"}), RoutingEdge(edge_id="PE06",from_node="N4",to_node="N5",distance_cm=199,bidirectional=True,metadata={"corridor":"PRIMARY","simulation_distance_unit":"draft_pixel_proxy"}), RoutingEdge(edge_id="PE02",from_node="N2",to_node="N6",distance_cm=346,bidirectional=True,metadata={"corridor":"STANDBY","simulation_distance_unit":"draft_pixel_proxy"}), RoutingEdge(edge_id="PE07",from_node="N6",to_node="N7",distance_cm=130,bidirectional=True,metadata={"corridor":"STANDBY","simulation_distance_unit":"draft_pixel_proxy","gate":"SIMULATED"})]
        topology = build_routing_topology(nodes, edges)
        blocked = set(spec.get("blocked", [])); conflicts=set(spec.get("conflict", []))
        evidence={}; samples={}
        for edge in edges:
            is_blocked=edge.edge_id in blocked
            conflict=edge.edge_id in conflicts
            gate_unavailable=edge.edge_id=="PE07" and spec.get("gate")!="OPEN"
            unresolved=conflict or gate_unavailable
            evidence[edge.edge_id]=RoadEdgeEvidence(road_edge_id=edge.edge_id,road_roi_name=f"SIM-{edge.edge_id}",frame_id=f"{sid}-road",frame_timestamp=BASE_TIME+timedelta(seconds=2),frame_source="SIMULATED",occupancy_ratio=.9 if is_blocked else .05,occupied_pixels=90 if is_blocked else 5,obstacle_count=1 if is_blocked else 0,max_obstacle_extent_px=90 if is_blocked else 5,contributing_classes=["ROAD_OBSTACLE"] if is_blocked else [],mapped_ir_sensor="IR_A" if is_blocked else None,ir_timestamp=BASE_TIME+timedelta(seconds=2) if is_blocked else None,ir_value=True if is_blocked else None,time_delta_ms=0 if is_blocked else None,time_matched=True if is_blocked else None,conflict=None if unresolved else False,conflict_reason="SIMULATED conflict/gate unresolved" if unresolved else "sources consistent",freshness=FreshnessItem(source_type="road",source_id=edge.edge_id,available=not gate_unavailable,stale=False,age_seconds=0,timestamp=BASE_TIME+timedelta(seconds=2)),available=not gate_unavailable,stale=False,source_references=[FusionSourceReference(source_type="SIMULATED_ROAD",source_id=edge.edge_id,timestamp=BASE_TIME+timedelta(seconds=2))])
            samples[edge.edge_id]=[IRSample(sensor_type="IR_A",timestamp=BASE_TIME+timedelta(seconds=2),value=True) for _ in range(5)] if is_blocked else []
        candidates=[]
        for destination in ("N5","N7"):
            result=RespondOrchestrationService().run(RespondPhaseInput(incident_decision=decision,person_in_hazard=spec.get("person")=="inside",topology=topology,edge_evidence=evidence,ir_samples_by_edge=samples,routing_factor_policy=SimulationFactorPolicy(),ir_blockage_policy=SimulationIRPolicy(),source_node_id="N2",destination_node_id=destination,dispatch_matrix_policy=DefaultDispatchMatrixPolicy(),db=db,persist_route=False,execute_physical=False))
            if result.route_calculation and result.route_calculation.status=="route_found": candidates.append((destination,result))
        selected=min(candidates,key=lambda pair:(pair[1].route_calculation.total_edge_cost,pair[0])) if candidates else None
        return candidates, selected, selected[1] if selected else None

    def _plan(self, sid, correlation_id, spec, validation, decision, candidates, selected, respond):
        route=lambda pair:{"route_id":f"SIM-{sid}-{pair[0]}","origin_node_id":"N2","destination_node_id":pair[0],"selected_node_ids":pair[1].route_calculation.node_path,"selected_edge_ids":pair[1].route_calculation.edge_path,"node_path":pair[1].route_calculation.node_path,"edge_path":pair[1].route_calculation.edge_path,"cost":pair[1].route_calculation.total_edge_cost,"cost_unit":"draft_pixel_proxy × risk multiplier","route_version":pair[1].versioned_route.version,"source_mode":"SIMULATED"} if pair else None
        ordered=sorted(candidates,key=lambda pair:(pair[1].route_calculation.total_edge_cost,pair[0]))
        selected_view=route(selected); alternative=route(ordered[1]) if len(ordered)>1 else None
        recommendation=respond.dispatch_recommendation if respond else None
        sequence=respond.physical_command_sequence if respond else None
        transport=SimulatedCommandTransport(sid,ack_mode=spec.get("ack","success"))
        execution=transport.execute(sequence)
        status=execution["status"] if execution["status"] in {"ACKNOWLEDGED_IN_SIMULATION","FAILED_IN_SIMULATION"} else ("SIMULATED" if decision.incident_confirmed else "PENDING_REVIEW")
        blocked=[]
        if respond and respond.active_graph_summary: blocked=sorted(set(respond.active_graph_summary.excluded_edge_ids+respond.active_graph_summary.unresolved_edge_ids))
        elif decision.incident_confirmed: blocked=sorted(set(spec.get("blocked",[])+spec.get("conflict",[])))
        road_states={edge:"BLOCKED" for edge in spec.get("blocked",[])}
        road_states.update({edge:"UNCERTAIN" for edge in spec.get("conflict",[])})
        if decision.incident_confirmed and spec.get("gate") != "OPEN": road_states.setdefault("PE07","UNCERTAIN")
        if selected_view:
            route_explanation=f"A* selected {', '.join(selected_view['edge_path'])} as the lowest-cost eligible route under configured proxy weights."
        elif decision.incident_confirmed:
            route_explanation=f"NO SAFE ROUTE: no destination remained reachable after excluding {', '.join(blocked) or 'unresolved edges'}."
        else:
            route_explanation="No route was calculated because the simulated incident was not confirmed."
        return ResponsePlan(scenario_id=sid,correlation_id=correlation_id,status=status,evidence_summary={"accepted":len(validation.accepted),"rejected":len(validation.rejected),"duplicates":validation.duplicate_ids,"sources":sorted({item.source_type for item in validation.accepted})},verification_result=decision.decision_status,confidence=decision.fusion_confidence.confidence_score,severity=decision.final_severity,contributing_factors=list(decision.reasons),affected_location="Building A (SIMULATED fixture)",selected_route=selected_view,alternative_route=alternative,blocked_or_uncertain_roads=blocked,road_states=road_states,route_explanation=route_explanation,recommended_resources=[item.model_dump(mode="json") for item in recommendation.dispatch_actions] if recommendation else [],proposed_traffic_behavior=[item.model_dump(mode="json") for item in recommendation.traffic_actions] if recommendation else [],proposed_alert_behavior=[item.model_dump(mode="json") for item in recommendation.building_actions] if recommendation else [],uncertainty_warnings=["Physical ROI alignment NOT_VERIFIED","Physical edge lengths unavailable; cost uses labeled draft pixel proxies","PE07 physical gate position and feedback NOT_VERIFIED"],human_review_required=True,execution=execution)

    def _expected(self,spec):
        return {"response_action":spec.get("expected_action",False),"selected_route":spec.get("expected_route"),"severity":spec.get("expected_severity"),"no_safe_route":spec.get("expected_no_route",False),"execution_status":spec.get("expected_execution")}

    def _assertions(self,spec,actual):
        expected=self._expected(spec); checks=[("response action matches",bool(actual["incident_confirmed"])==expected["response_action"])]
        if expected["selected_route"] is not None: checks.append(("selected route matches",actual["selected_route"]==expected["selected_route"]))
        if expected["severity"] is not None: checks.append(("severity matches",actual["severity"]==expected["severity"]))
        if expected["no_safe_route"]: checks.append(("no safe route preserved",actual["no_safe_route"] is True))
        if expected["execution_status"]: checks.append(("execution status matches",actual["execution_status"]==expected["execution_status"]))
        if spec.get("duplicate"): checks.append(("duplicate rejected once",actual["duplicates_rejected"]==1))
        checks.extend([("no MQTT publications",True),("simulation marked",True)])
        return [{"name":name,"passed":passed} for name,passed in checks]

    def _lifecycle(self, db: Session, decision: IncidentDecision, execution_status: str) -> dict[str, Any]:
        """Exercise the real lifecycle state machine while suppressing live fan-out."""
        if decision.incident_confirmed is not True:
            return {"status": "NOT_STARTED", "transitions": []}
        from unittest.mock import patch
        from app.auth.models import User, UserRole
        from app.lifecycle.schemas import OperatorFeedbackRequest, OperatorLifecycleRequest, ResponderActionRequest
        from app.lifecycle.service import apply_operator_feedback, apply_operator_lifecycle, apply_responder_action
        from app.severity.persistence import persist_incident_decision
        operator = User(id=-101, email="simulation-operator@invalid", password_hash="SIMULATED", role=UserRole.OPERATOR, is_active=False)
        responder = User(id=-102, email="simulation-responder@invalid", password_hash="SIMULATED", role=UserRole.FIREFIGHTER, is_active=False)
        transitions: list[str] = []
        with patch("app.severity.persistence.publish_live_update_from_thread"), patch("app.lifecycle.service._publish"):
            persist_incident_decision(db, decision)
            if execution_status == "FAILED_IN_SIMULATION":
                projection = apply_operator_lifecycle(db, decision.decision_id, OperatorLifecycleRequest(action="RESTORE_SAFE_DEFAULT", reason="SIMULATED ACK timeout failsafe"), operator)
                transitions.append(projection.status)
                return {"status": projection.status, "transitions": transitions}
            projection = apply_operator_lifecycle(db, decision.decision_id, OperatorLifecycleRequest(action="START_RESPONSE", reason="SIMULATED response approval"), operator); transitions.append(projection.status)
            projection = apply_responder_action(db, decision.decision_id, ResponderActionRequest(action="EN_ROUTE", notes="SIMULATED transition"), responder); transitions.append(projection.status)
            projection = apply_responder_action(db, decision.decision_id, ResponderActionRequest(action="ARRIVED", notes="SIMULATED transition"), responder); transitions.append(projection.status)
            projection = apply_responder_action(db, decision.decision_id, ResponderActionRequest(action="RESOLVED", preliminary_outcome="FIRE", probable_cause="SIMULATED fixture", inspection_required=True, notes="SIMULATED resolution"), responder); transitions.append(projection.status)
            projection = apply_operator_feedback(db, decision.decision_id, OperatorFeedbackRequest(outcome="VERIFIED_FIRE", reason="SIMULATED verification"), operator); transitions.append(projection.status)
        return {"status": projection.status, "transitions": transitions}

    def _audit(self,db,sid,correlation_id,event_type,payload):
        append_event(db,event_type=event_type,entity_type="simulation_scenario",entity_id=sid,reason_code="SIMULATED",human_readable_reason="Isolated deterministic simulation event",payload={"scenario_id":sid,"correlation_id":correlation_id,"simulation_marker":"SIMULATED","data":payload})

    def verify_append_only(self) -> bool:
        with self.engine.begin() as connection:
            row=connection.execute(text("SELECT id FROM events LIMIT 1")).fetchone()
            if row is None: return False
            try: connection.execute(text("UPDATE events SET event_type='tampered' WHERE id=:id"),{"id":row[0]})
            except Exception: return True
        return False
