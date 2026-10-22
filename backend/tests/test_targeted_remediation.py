"""Regression coverage for the targeted FV-028/029/031-034/036/037/039 fixes."""

import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth.models import UserRole
from app.core.database import Base
from app.dispatch.matrix import DispatchInput
from app.dispatch.policies import DefaultDispatchMatrixPolicy
from app.events.models import Event, IncidentTransitionClaim
from app.fusion.schemas import FusionConfidenceResult
from app.physical_actions.execution import (
    PhysicalSequenceExecutionResult,
    _execute_normal_with_ack,
)
from app.physical_actions.schemas import ActionCategory, ActionType, PhysicalActionCommandSpec
from app.physical_actions.mapper import map_dispatch_recommendation
from app.physical_actions.sequence import SequencePhase, sequence_physical_actions
from app.respond.service import (
    RespondOrchestrationService,
    RespondPhaseInput,
    _selected_corridor_for_route,
)
from app.routing.state import CameraFrame, EdgeState, fuse_sensor_data
from app.routing.freshness import validate_traffic_command_route_version
from app.routing.persistence import persist_versioned_route
from app.routing.route import RouteCalculationResult
from app.routing.topology import RoutingEdge, RoutingNode, RoutingTopology
from app.routing.versioning import version_route
from app.severity.decision import IncidentDecision
from app.severity.operator import (
    OperatorAction,
    OperatorDecisionRequest,
    create_operator_decision,
)
from app.severity.persistence import (
    IncidentTransitionConflict,
    persist_incident_decision,
    persist_operator_decision,
)


def _incident(*, confirmed: bool = False, severity: str | None = None) -> IncidentDecision:
    now = datetime.now(timezone.utc)
    return IncidentDecision.model_construct(
        decision_id=f"incident-{now.timestamp()}",
        evaluated_at=now,
        confirmation_status="confirmed" if confirmed else "not_confirmed",
        incident_confirmed=confirmed,
        confirmation_windows=[],
        fusion_confidence=FusionConfidenceResult(
            status="not_calculated",
            weights={},
            weighted_contributions={},
            calculated_at=now,
        ),
        severity_score=None,
        base_severity=severity,
        final_severity=severity,
        critical_override_applied=False,
        decision_status="confirmed" if confirmed else "not_confirmed",
        reasons=[],
        warnings=[],
        audit_references=[],
    )


def _operator_result(incident: IncidentDecision, action: OperatorAction):
    return create_operator_decision(
        incident,
        OperatorDecisionRequest(
            operator_id=1,
            operator_role=UserRole.OPERATOR,
            action=action,
            written_reason="controlled targeted validation",
            severity_floor="MEDIUM" if action is OperatorAction.CONFIRM else None,
        ),
    )


def _database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'targeted.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_fv028_conflict_grace_is_1_5_seconds():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    edge = EdgeState(edge_id="main")
    edge.camera_window = [CameraFrame(started, 0.0, 0.0, 0.0)]
    edge.ir_state = "BLOCKED"
    edge.ir_last_timestamp = started

    fuse_sensor_data(edge, started)
    fuse_sensor_data(edge, started + timedelta(seconds=1.49))
    assert edge.current_state == "OPEN"

    fuse_sensor_data(edge, started + timedelta(seconds=1.5))
    assert edge.current_state == "SENSOR_CONFLICT"


def test_fv029_recovery_holds_unavailable_edge_for_five_seconds():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    edge = EdgeState(
        edge_id="main",
        current_state="SENSOR_CONFLICT",
        unavailable_since=started,
        ir_state="OPEN",
    )

    before = started + timedelta(seconds=4.99)
    edge.camera_window = [CameraFrame(before, 0.0, 0.0, 0.0)]
    edge.ir_last_timestamp = before
    fuse_sensor_data(edge, before)
    assert edge.current_state == "SENSOR_CONFLICT"

    after = started + timedelta(seconds=5.0)
    edge.camera_window = [CameraFrame(after, 0.0, 0.0, 0.0)]
    edge.ir_last_timestamp = after
    fuse_sensor_data(edge, after)
    assert edge.current_state == "OPEN"


def test_fv031_operator_floor_is_required_and_preserved():
    incident = _incident()
    try:
        create_operator_decision(
            incident,
            OperatorDecisionRequest(
                operator_id=1,
                operator_role=UserRole.OPERATOR,
                action=OperatorAction.CONFIRM,
                written_reason="confirm without calculated R",
            ),
        )
    except ValueError as exc:
        assert "severity_floor is required" in str(exc)
    else:
        raise AssertionError("missing severity floor was accepted")

    result = _operator_result(incident, OperatorAction.CONFIRM)
    assert result.severity_floor == "MEDIUM"


def _check_fv032_fv033_release_sequence_matches_current_schema(tmp_path, action):
    engine, sessions = _database(tmp_path)
    db = sessions()
    try:
        incident = _incident()
        now = datetime.now(timezone.utc)

        def fake_release(_db, _specs, sequence_id, _route=None):
            return PhysicalSequenceExecutionResult(
                sequence_id=sequence_id,
                status="safe_default_applied",
                route_id=None,
                route_version=None,
                command_results=[],
                started_at=now,
                completed_at=now,
                duration_ms=0.0,
            )

        with patch("app.respond.service._run_safe_defaults", fake_release):
            result = RespondOrchestrationService().run(
                RespondPhaseInput(
                    incident_decision=incident,
                    operator_actions=[_operator_result(incident, action)],
                    topology=RoutingTopology(nodes=[], edges=[]),
                    source_node_id="station",
                    destination_node_id="target",
                    db=db,
                    execute_physical=True,
                )
            )
        assert result.status == action.value.lower()
        assert result.physical_command_sequence is not None
        assert result.physical_command_sequence.status == "planned"
        assert len(result.physical_command_sequence.ordered_command_specs) == 3
    finally:
        db.close()
        engine.dispose()


def test_fv034_database_claim_allows_one_confirmation_winner(tmp_path):
    engine, sessions = _database(tmp_path)
    initial = sessions()
    incident = _incident()
    try:
        persist_incident_decision(initial, incident)
    finally:
        initial.close()

    decisions = [
        _operator_result(incident, OperatorAction.CONFIRM),
        _operator_result(incident, OperatorAction.CONFIRM),
    ]

    def persist(decision):
        db = sessions()
        try:
            persist_operator_decision(db, decision)
            return "won"
        except IncidentTransitionConflict:
            return "ignored"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(persist, decisions))

    verify = sessions()
    try:
        assert sorted(outcomes) == ["ignored", "won"]
        assert len(verify.scalars(select(IncidentTransitionClaim)).all()) == 1
        assert len(
            verify.scalars(
                select(Event).where(Event.event_type == "operator_decision")
            ).all()
        ) == 1
        assert len(
            verify.scalars(
                select(Event).where(Event.event_type == "operator_decision_ignored")
            ).all()
        ) == 1
    finally:
        verify.close()
        engine.dispose()


def test_fv034_late_confirm_is_logged_and_rejected_after_automatic_win(tmp_path):
    engine, sessions = _database(tmp_path)
    db = sessions()
    incident = _incident(confirmed=True, severity="HIGH")
    try:
        persist_incident_decision(db, incident)
        late_confirm = _operator_result(incident, OperatorAction.CONFIRM)
        with raises_transition_conflict():
            persist_operator_decision(db, late_confirm)
        ignored = db.scalars(
            select(Event).where(Event.event_type == "operator_decision_ignored")
        ).all()
        assert len(ignored) == 1
        assert ignored[0].reason_code == "CONFIRM_IGNORED_ALREADY_CONFIRMED"
    finally:
        db.close()
        engine.dispose()


class raises_transition_conflict:
    """Small dependency-free assertion context for the expected lock conflict."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, _traceback):
        if exc_type is None:
            raise AssertionError("late confirmation unexpectedly persisted")
        if not issubclass(exc_type, IncidentTransitionConflict):
            return False
        return True


def _check_fv036_low_matches_master_contract():
    recommendation = DefaultDispatchMatrixPolicy().evaluate(
        DispatchInput(
            incident_decision_id="targeted",
            incident_confirmed=True,
            final_severity="LOW",
            person_in_hazard=False,
        )
    )
    assert recommendation.dispatch_actions[0].action_type == "HOLD_UNIT"
    assert recommendation.dispatch_actions[0].parameters["unit_id"] == "E1"
    assert recommendation.traffic_actions[0].action_type == "NORMAL_CYCLE"
    assert recommendation.building_actions[0].action_type == "ZONE_AMBER_5_SECONDS"
    assert not any(
        action.action_category in {ActionCategory.GATE, ActionCategory.BUZZER}
        for action in recommendation.building_actions
    )


def _medium_recommendation(corridor):
    return DefaultDispatchMatrixPolicy().evaluate(
        DispatchInput(
            incident_decision_id="targeted",
            incident_confirmed=True,
            final_severity="MEDIUM",
            person_in_hazard=False,
            selected_corridor=corridor,
        )
    )


def _check_fv037_medium_matches_master_contract(corridor):
    recommendation = _medium_recommendation(corridor)
    assert recommendation.dispatch_actions[0].parameters == {
        "unit_id": "E1",
        "unit_type": "FIRE_UNIT",
        "count": 1,
    }
    traffic = recommendation.traffic_actions[0]
    assert traffic.action_type == "GREEN_CORRIDOR"
    assert traffic.parameters["corridor"] == corridor
    assert any(
        action.action_category is ActionCategory.BUZZER
        and action.action_type == "PULSE_500_MS"
        for action in recommendation.building_actions
    )
    assert any(
        action.action_type == "ZONE_AMBER_ON"
        for action in recommendation.building_actions
    )
    assert not any(
        action.action_category is ActionCategory.GATE
        for action in recommendation.building_actions
    )

    plan = map_dispatch_recommendation(
        recommendation,
        route_id="route-1",
        route_version=2,
    )
    sequence = sequence_physical_actions(plan)
    assert sequence.status == "planned"
    assert sequence.phases[0].phase is SequencePhase.SAFETY_TRANSITION
    assert sequence.phases[0].command_specs[0].action_type is ActionType.ALL_RED
    assert sequence.phases[0].delay_after_ms == 1000
    assert sequence.phases[1].phase is SequencePhase.TRAFFIC_CORRIDOR
    corridor_spec = sequence.phases[1].command_specs[0]
    assert corridor_spec.parameters["corridor"] == corridor
    assert corridor_spec.route_version == 2


def test_fv039_retry_reuses_command_id():
    published_ids = []
    payloads = []
    ack_count = 0

    def fake_publish(_db, *, node_id, command_type, payload, command_id=None):
        published_ids.append(command_id)
        payloads.append(payload)
        return {
            "command_id": command_id or "logical-command-id",
            "node_id": node_id,
            "command_type": command_type,
            "payload": payload,
        }

    async def fake_wait(command_id, node_id):
        nonlocal ack_count
        ack_count += 1
        return SimpleNamespace(
            ack_received=ack_count == 2,
            status="acknowledged" if ack_count == 2 else "timeout",
            latency_ms=10.0 if ack_count == 2 else None,
            completed_at=datetime.now(timezone.utc),
        )

    spec = PhysicalActionCommandSpec(
        action_category=ActionCategory.BUZZER,
        action_type=ActionType.ON,
    )
    with patch(
        "app.physical_actions.execution.publish_actuator_command", fake_publish
    ), patch(
        "app.physical_actions.execution.wait_for_actuator_ack", fake_wait
    ):
        result = asyncio.run(
            _execute_normal_with_ack(None, SequencePhase.BUILDING_RESPONSE, spec)
        )

    assert result.status == "acknowledged_after_retry"
    assert published_ids == [None, "logical-command-id"]
    assert [attempt.command_id for attempt in result.attempts] == [
        "logical-command-id",
        "logical-command-id",
    ]
    assert payloads[1]["retry_of_command_id"] == "logical-command-id"


def _route_result(edge_path):
    now = datetime.now(timezone.utc)
    return RouteCalculationResult(
        status="route_found",
        source_node_id="station",
        destination_node_id="incident",
        node_path=["station", *edge_path, "incident"],
        edge_path=edge_path,
        total_edge_cost=1.0,
        total_distance_cm=1.0,
        no_safe_route=False,
        calculation_duration_ms=0.0,
        calculated_at=now,
    )


def test_route_version_increment_and_stale_corridor_rejection(tmp_path):
    engine, sessions = _database(tmp_path)
    db = sessions()
    try:
        primary = version_route(_route_result(["primary-edge"]))
        standby = version_route(
            _route_result(["standby-edge"]),
            previous_route=primary,
            route_id=primary.route_id,
        )
        assert standby.version == primary.version + 1
        assert standby.invalidates_prior_commands is True
        persist_versioned_route(db, primary)
        persist_versioned_route(db, standby)
        stale = PhysicalActionCommandSpec(
            action_category=ActionCategory.TRAFFIC,
            action_type=ActionType.GREEN_CORRIDOR,
            route_id=primary.route_id,
            route_version=primary.version,
            parameters={"corridor": "PRIMARY"},
        )
        result = validate_traffic_command_route_version(db, stale)
        assert result.status == "stale_route_version"
        assert result.invalidated is True
        assert result.latest_route_version == standby.version
    finally:
        db.close()
        engine.dispose()


def test_selected_route_metadata_resolves_primary_and_standby_corridors():
    topology = RoutingTopology(
        nodes=[
            RoutingNode(node_id="station"),
            RoutingNode(node_id="incident"),
        ],
        edges=[
            RoutingEdge(
                edge_id="primary-edge",
                from_node="station",
                to_node="incident",
                distance_cm=1.0,
                bidirectional=True,
                metadata={"corridor": "PRIMARY"},
            ),
            RoutingEdge(
                edge_id="standby-edge",
                from_node="station",
                to_node="incident",
                distance_cm=1.0,
                bidirectional=True,
                metadata={"corridor": "STANDBY"},
            ),
        ],
    )
    primary = version_route(_route_result(["primary-edge"]))
    standby = version_route(
        _route_result(["standby-edge"]),
        previous_route=primary,
        route_id=primary.route_id,
    )

    assert _selected_corridor_for_route(primary, topology) == "PRIMARY"
    assert _selected_corridor_for_route(standby, topology) == "STANDBY"


class TargetedRemediationTests(unittest.TestCase):
    def test_fv028(self):
        test_fv028_conflict_grace_is_1_5_seconds()

    def test_fv029(self):
        test_fv029_recovery_holds_unavailable_edge_for_five_seconds()

    def test_fv031(self):
        test_fv031_operator_floor_is_required_and_preserved()

    def test_fv032(self):
        with tempfile.TemporaryDirectory() as directory:
            _check_fv032_fv033_release_sequence_matches_current_schema(
                Path(directory), OperatorAction.REJECT
            )

    def test_fv033(self):
        with tempfile.TemporaryDirectory() as directory:
            _check_fv032_fv033_release_sequence_matches_current_schema(
                Path(directory), OperatorAction.CANCEL
            )

    def test_fv034(self):
        with tempfile.TemporaryDirectory() as directory:
            test_fv034_database_claim_allows_one_confirmation_winner(Path(directory))

    def test_fv034_automatic_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            test_fv034_late_confirm_is_logged_and_rejected_after_automatic_win(
                Path(directory)
            )

    def test_fv036(self):
        _check_fv036_low_matches_master_contract()

    def test_fv037(self):
        _check_fv037_medium_matches_master_contract("PRIMARY")

    def test_fv037_standby_corridor(self):
        _check_fv037_medium_matches_master_contract("STANDBY")

    def test_fv039(self):
        test_fv039_retry_reuses_command_id()

    def test_route_version_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            test_route_version_increment_and_stale_corridor_rejection(
                Path(directory)
            )

    def test_route_to_physical_corridor_mapping(self):
        test_selected_route_metadata_resolves_primary_and_standby_corridors()


if __name__ == "__main__":
    unittest.main()
