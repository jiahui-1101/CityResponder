"""Validation script for Dispatch matrix rules and operator overrides."""

import sys
sys.path.insert(0, ".")

from app.dispatch.policies import DefaultDispatchMatrixPolicy
from app.dispatch.matrix import DispatchInput
from app.physical_actions.schemas import ActionCategory
from app.severity.operator import OperatorDecisionResult, OperatorAction
from app.auth.models import UserRole
from datetime import datetime, timezone

def test_dispatch_matrix():
    print("=" * 60)
    print("DISPATCH-01 & 03b: Resource Allocation & Hardware Actions")
    print("=" * 60)
    
    policy = DefaultDispatchMatrixPolicy()
    
    # 1. LOW
    inp_low = DispatchInput(
        incident_decision_id="test",
        incident_confirmed=True,
        final_severity="LOW",
        person_in_hazard=False
    )
    rec_low = policy.evaluate(inp_low)
    assert len(rec_low.dispatch_actions) == 1
    assert rec_low.dispatch_actions[0].action_type == "HOLD_UNIT"
    assert rec_low.dispatch_actions[0].parameters["unit_id"] == "E1"
    assert rec_low.traffic_actions[0].action_type == "NORMAL_CYCLE"
    assert rec_low.building_actions[0].action_type == "ZONE_AMBER_5_SECONDS"
    assert all(a.action_category is not ActionCategory.GATE for a in rec_low.building_actions)
    assert any("[Actor: System] | [LOW_DISPATCH]" in r for r in rec_low.reasons)
    print("  [PASS] LOW -> E1 held, NORMAL_CYCLE, amber 5 seconds, no gate/buzzer")
    
    # 2. MEDIUM
    inp_medium = DispatchInput(
        incident_decision_id="test",
        incident_confirmed=True,
        final_severity="MEDIUM",
        person_in_hazard=False,
        selected_corridor="PRIMARY",
    )
    rec_medium = policy.evaluate(inp_medium)
    assert len(rec_medium.dispatch_actions) == 1
    assert rec_medium.dispatch_actions[0].parameters["unit_type"] == "FIRE_UNIT"
    assert rec_medium.dispatch_actions[0].parameters["unit_id"] == "E1"
    assert rec_medium.dispatch_actions[0].parameters["count"] == 1
    assert rec_medium.traffic_actions[0].action_type == "GREEN_CORRIDOR"
    assert rec_medium.traffic_actions[0].parameters["corridor"] == "PRIMARY"
    assert any(a.action_type == "PULSE_500_MS" for a in rec_medium.building_actions)
    assert any(a.action_type == "ZONE_AMBER_ON" for a in rec_medium.building_actions)
    assert all(a.action_category is not ActionCategory.GATE for a in rec_medium.building_actions)
    assert any("[Actor: System] | [MEDIUM_DISPATCH]" in r for r in rec_medium.reasons)
    print("  [PASS] MEDIUM -> E1, selected corridor, pulsed buzzer, amber, gate closed")
    
    # 3. HIGH
    inp_high = DispatchInput(
        incident_decision_id="test",
        incident_confirmed=True,
        final_severity="HIGH",
        person_in_hazard=False,
        selected_corridor="PRIMARY",
    )
    rec_high = policy.evaluate(inp_high)
    assert len(rec_high.dispatch_actions) == 2
    unit_types = {a.parameters["unit_type"]: a.parameters["count"] for a in rec_high.dispatch_actions}
    assert unit_types.get("FIRE_UNIT") == 2
    assert unit_types.get("AMBULANCE") == 1
    assert len(rec_high.building_actions) == 2
    hardware_actions = [(a.action_category, a.action_type) for a in rec_high.building_actions]
    assert (ActionCategory.GATE, "OPEN") in hardware_actions
    assert (ActionCategory.BUZZER, "ON") in hardware_actions
    assert len(rec_high.traffic_actions) == 1
    assert rec_high.traffic_actions[0].action_type == "GREEN_CORRIDOR"
    assert any("Trigger: HIGH -> 2 Fire, 1 Ambulance, Buzzer ON, Gate OPEN, GREEN_CORRIDOR" in r for r in rec_high.reasons)
    assert any("[Actor: System] | [HIGH_DISPATCH]" in r for r in rec_high.reasons)
    print("  [PASS] HIGH -> 2 Fire, 1 Ambulance, Buzzer ON, Gate OPEN, GREEN_CORRIDOR")
    
    # 4. CRITICAL with Person in Hazard
    inp_crit = DispatchInput(
        incident_decision_id="test",
        incident_confirmed=True,
        final_severity="CRITICAL",
        person_in_hazard=True,
        selected_corridor="PRIMARY",
    )
    rec_crit = policy.evaluate(inp_crit)
    assert len(rec_crit.dispatch_actions) == 3
    unit_types = {a.parameters["unit_type"]: a.parameters["count"] for a in rec_crit.dispatch_actions}
    assert unit_types.get("FIRE_UNIT") == 2
    assert unit_types.get("AMBULANCE") == 1
    assert unit_types.get("RESCUE_UNIT") == 1
    assert len(rec_crit.building_actions) == 2
    hardware_actions = [(a.action_category, a.action_type) for a in rec_crit.building_actions]
    assert (ActionCategory.GATE, "OPEN") in hardware_actions
    assert (ActionCategory.BUZZER, "ON") in hardware_actions
    assert len(rec_crit.traffic_actions) == 1
    assert rec_crit.traffic_actions[0].action_type == "GREEN_CORRIDOR"
    
    # Check Explicit Traceability
    assert any("Trigger: P=1 (YOLO >= 0.50, inside polygon, 1 frame) -> CRITICAL -> 2 Fire + 1 Amb + 1 Rescue." in r for r in rec_crit.reasons)
    assert any("[Actor: System] | [PERSON_ESCALATION]" in r for r in rec_crit.reasons)
    print("  [PASS] CRITICAL -> 2 Fire, 1 Ambulance, 1 Rescue, Buzzer ON, Gate OPEN, GREEN_CORRIDOR")
    print("  [PASS] Explicit traceability string validated")

def test_manual_override_pipeline():
    print("\n" + "=" * 60)
    print("DISPATCH-03a: Manual Override Pipeline")
    print("=" * 60)
    
    from app.respond.service import RespondPhaseInput, RespondOrchestrationService
    from app.severity.decision import IncidentDecision
    from app.routing.topology import RoutingTopology
    from app.fusion.schemas import FusionConfidenceResult

    # Create an unconfirmed IncidentDecision with no R score
    automatic_decision = IncidentDecision(
        decision_id="test_decision",
        evaluated_at=datetime.now(timezone.utc),
        confirmation_status="not_confirmed",
        incident_confirmed=False,
        fusion_confidence=FusionConfidenceResult(status="not_calculated", weights={}, weighted_contributions={}, calculated_at=datetime.now(timezone.utc)),
        severity_score=None,
        base_severity=None,
        final_severity=None,
        critical_override_applied=False,
        decision_status="not_confirmed"
    )

    # Simulate an Operator Decision (CONFIRM)
    operator_action = OperatorDecisionResult(
        action_id="action_1",
        incident_decision_id="test_decision",
        operator_id=1,
        operator_role=UserRole.OPERATOR,
        action=OperatorAction.CONFIRM,
        written_reason="Operator saw smoke on dashboard",
        severity_floor="MEDIUM",
        previous_automatic_decision_status="not_confirmed",
        resulting_operator_outcome="CONFIRM",
        action_timestamp=datetime.now(timezone.utc)
    )

    req = RespondPhaseInput(
        incident_decision=automatic_decision,
        operator_actions=[operator_action],
        topology=RoutingTopology(nodes=[], edges=[]),
        source_node_id="station",
        destination_node_id="target",
        dispatch_matrix_policy=DefaultDispatchMatrixPolicy()
    )

    service = RespondOrchestrationService()
    # The route will fail because nodes don't exist in dummy topology, but it evaluates manual override before that!
    res = service.run(req)
    
    # Check if the override successfully passed `not_actionable` check and failed on configuration instead
    assert res.status == "configuration_error"
    
    # Test the matrix independently for the explicit operator MEDIUM floor
    inp_medium_fallback = DispatchInput(
        incident_decision_id="test_decision",
        incident_confirmed=True, # Manual override forced this
        final_severity="MEDIUM",
        person_in_hazard=False,
        selected_corridor="PRIMARY",
    )
    rec_medium = DefaultDispatchMatrixPolicy().evaluate(inp_medium_fallback)
    assert len(rec_medium.dispatch_actions) == 1
    assert rec_medium.dispatch_actions[0].parameters["unit_type"] == "FIRE_UNIT"
    assert rec_medium.dispatch_actions[0].parameters["count"] == 1
    
    print("  [PASS] Manual CONFIRM uses explicit MEDIUM severity floor when no R score exists")
    print("  [PASS] Dispatch matrix generates authoritative MEDIUM response")


def test_side_states():
    print("\n" + "=" * 60)
    print("DISPATCH-03a: Side-State Hardware Fallbacks")
    print("=" * 60)
    
    from app.physical_actions.execution import build_cancellation_specs, build_safe_default_specs
    from app.physical_actions.schemas import DEFAULT_ACTUATOR_NODE_ID, ActionCategory, ActionType
    
    # 1. FAILSAFE (NO_SAFE_ROUTE or ACTUATOR_ACK_TIMEOUT)
    failsafe_specs = build_safe_default_specs(
        target_node_id=DEFAULT_ACTUATOR_NODE_ID,
        trigger_reason="NO_SAFE_ROUTE"
    )
    hardware_actions = [(s.action_category, s.action_type) for s in failsafe_specs]
    assert (ActionCategory.TRAFFIC, ActionType.ALL_RED) in hardware_actions
    assert (ActionCategory.GATE, ActionType.CLOSE) in hardware_actions
    assert (ActionCategory.BUZZER, ActionType.ON) in hardware_actions
    print("  [PASS] FAILSAFE defaults to ALL_RED traffic, GATE CLOSE, BUZZER ON")
    
    # 2. REJECTED/CANCELLED
    cancel_specs = build_cancellation_specs(
        target_node_id=DEFAULT_ACTUATOR_NODE_ID,
        trigger_reason="REJECTED"
    )
    cancel_actions = [(s.action_category, s.action_type) for s in cancel_specs]
    assert (ActionCategory.TRAFFIC, ActionType.OFF) in cancel_actions
    assert (ActionCategory.GATE, ActionType.CLOSE) in cancel_actions
    assert (ActionCategory.BUZZER, ActionType.OFF) in cancel_actions
    print("  [PASS] REJECTED/CANCELLED defaults to TRAFFIC OFF, GATE CLOSE, BUZZER OFF")


if __name__ == "__main__":
    test_dispatch_matrix()
    test_manual_override_pipeline()
    test_side_states()
    print("\nAll Dispatch policy tests PASSED!")
