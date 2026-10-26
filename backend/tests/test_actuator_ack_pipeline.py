"""Isolated AC1 MQTT ACK contract tests; no broker or hardware is contacted."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.actuators import handlers
from app.actuators.ack_waiter import (
    clear_ack_waiter_state,
    wait_for_actuator_ack,
)
from app.actuators.projection import get_actuator_status
from app.actuators.schemas import ActuatorCommand
from app.actuators.service import publish_actuator_command
from app.core.database import Base
from app.events.models import Event
from app.events.repository import append_event, get_events_for_entity
from app.mqtt.client import MQTTClient
from app.physical_actions.execution import _execute_normal_with_ack
from app.physical_actions.schemas import ActionCategory, ActionType, PhysicalActionCommandSpec
from app.physical_actions.sequence import SequencePhase


@pytest.fixture
def ack_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    clear_ack_waiter_state()
    monkeypatch.setattr(handlers, "SessionLocal", factory)
    monkeypatch.setattr(handlers, "publish_live_update_from_thread", lambda _event: None)
    monkeypatch.setattr("app.actuators.service.publish_live_update_from_thread", lambda _event: None)

    class FakePublisher:
        def __init__(self):
            self.published = []

        def publish_confirmed(self, topic, payload, *, qos=1):
            self.published.append((topic, payload, qos))

    publisher = FakePublisher()
    monkeypatch.setattr("app.actuators.service.mqtt_client", publisher)
    yield db, factory, publisher
    clear_ack_waiter_state()
    db.close()
    engine.dispose()


def _command(db, publisher, *, command_id=None, node_id="AC1", action="ON", category="BUZZER"):
    command = publish_actuator_command(
        db,
        node_id=node_id,
        command_type="PHYSICAL_ACTION",
        payload={
            "action_category": category,
            "action_type": action,
            "parameters": {},
            "spec_id": "isolated-test-spec",
            "attempt_number": 1,
            "safe_default": False,
        },
        command_id=command_id,
    )
    assert publisher.published[-1][2] == 1
    return command


def _ack(command, *, status="ACK", stage="execution_reported", node_id=None, **extra):
    body = {
        "command_id": command["command_id"],
        "node_id": node_id or command["node_id"],
        "status": status,
        "stage": stage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_category": command["payload"].get("action_category"),
        "action_type": command["payload"].get("action_type"),
    }
    body.update(extra)
    return body


def _accepted_events(db, command_id):
    return [
        event
        for event in get_events_for_entity(db, entity_type="command", entity_id=command_id)
        if event.event_type == "actuator_ack"
    ]


def test_01_valid_command_publish_records_broker_stage_only(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    assert publisher.published[-1][0] == "city/commands/AC1"
    events = get_events_for_entity(db, entity_type="command", entity_id=command["command_id"])
    confirmed = next(event for event in events if event.event_type == "actuator_command_published")
    assert confirmed.payload["broker_confirmed"] is True
    assert confirmed.payload["device_received"] is False
    assert confirmed.payload["retained"] is False


def test_02_device_receipt_does_not_finish_wait_but_execution_ack_does(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)

    async def exercise():
        waiter = asyncio.create_task(wait_for_actuator_ack(command["command_id"], "AC1"))
        await asyncio.sleep(0)
        handlers.handle_ack_message("city/acks/AC1", _ack(command, status="RECEIVED", stage="received"))
        await asyncio.sleep(0.01)
        assert not waiter.done()
        handlers.handle_ack_message("city/acks/AC1", _ack(command))
        result = await waiter
        assert result.status == "acknowledged"
        assert result.ack_received is True

    asyncio.run(exercise())
    assert [event.payload["ack_stage"] for event in reversed(_accepted_events(db, command["command_id"]))] == [
        "received",
        "execution_reported",
    ]


def test_03_missing_ack_times_out_without_fabricating_success(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    result = asyncio.run(wait_for_actuator_ack(command["command_id"], "AC1"))
    assert result.status == "timeout"
    assert result.ack_received is False


def test_04_timeout_is_distinct_from_late_ack(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    first = asyncio.run(wait_for_actuator_ack(command["command_id"], "AC1"))
    assert first.status == "timeout"
    append_event(
        db,
        event_type="actuator_ack_timeout",
        entity_type="command",
        entity_id=command["command_id"],
        payload={"command_id": command["command_id"], "retry_decision": "retry_same_command_id"},
    )
    handlers.handle_ack_message("city/acks/AC1", _ack(command))
    second = asyncio.run(wait_for_actuator_ack(command["command_id"], "AC1"))
    assert second.status == "late_acknowledged"
    assert second.ack_received is True


def test_05_duplicate_terminal_ack_is_idempotent(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    body = _ack(command)
    handlers.handle_ack_message("city/acks/AC1", body)
    handlers.handle_ack_message("city/acks/AC1", body)
    assert len(_accepted_events(db, command["command_id"])) == 1


def test_06_unknown_command_ack_is_rejected(ack_db):
    db, _factory, _publisher = ack_db
    unknown = {"command_id": str(uuid4()), "node_id": "AC1", "status": "ACK", "timestamp": datetime.now(timezone.utc).isoformat()}
    handlers.handle_ack_message("city/acks/AC1", unknown)
    assert not _accepted_events(db, unknown["command_id"])
    assert any(event.event_type == "actuator_ack_rejected" for event in get_events_for_entity(db, entity_type="command", entity_id=unknown["command_id"]))


def test_07_wrong_device_id_cannot_confirm_command(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/OTHER", _ack(command, node_id="OTHER"))
    assert not _accepted_events(db, command["command_id"])


def test_08_ack_topic_must_match_payload_device(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/OTHER", _ack(command))
    assert not _accepted_events(db, command["command_id"])


def test_09_malformed_ack_is_safely_rejected(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", {**_ack(command), "status": "SUCCESS"})
    assert not _accepted_events(db, command["command_id"])


def test_10_mqtt_reconnect_resubscribes_ack_handler():
    client = MQTTClient()

    class FakeClient:
        def __init__(self):
            self.subscribed = []

        def is_connected(self):
            return False

        def subscribe(self, topic, qos):
            self.subscribed.append((topic, qos))
            return 0, 1

    fake = FakeClient()
    client._client = fake
    client.subscribe("city/acks/#", lambda _topic, _payload: None)
    client._on_connect(fake, None, None, 0, None)
    client._connected_event.clear()
    client._on_connect(fake, None, None, 0, None)
    assert fake.subscribed == [("city/acks/#", 1), ("city/acks/#", 1)]


def test_11_device_restart_during_gate_command_stays_unknown_and_is_not_resent(monkeypatch):
    """Model lost volatile ESP32 dedup state with no device ACK after reset."""
    command_ids = []

    def fake_publish(_db, *, node_id, command_type, payload, command_id=None):
        command_ids.append(command_id)
        return {"command_id": command_id or "gate-test-id", "node_id": node_id, "command_type": command_type, "payload": payload}

    async def fake_wait(_command_id, _node_id):
        return SimpleNamespace(status="timeout", ack_received=False, ack_payload=None, latency_ms=None, completed_at=datetime.now(timezone.utc))

    spec = PhysicalActionCommandSpec(action_category=ActionCategory.GATE, action_type=ActionType.OPEN)
    monkeypatch.setattr("app.physical_actions.execution.publish_actuator_command", fake_publish)
    monkeypatch.setattr("app.physical_actions.execution.wait_for_actuator_ack", fake_wait)
    result = asyncio.run(_execute_normal_with_ack(None, SequencePhase.BUILDING_RESPONSE, spec))
    assert result.status == "execution_unknown"
    assert len(command_ids) == 1


def test_12_broker_disconnect_is_publish_failure_not_device_timeout(ack_db, monkeypatch):
    db, _factory, _publisher = ack_db

    class Disconnected:
        def publish_confirmed(self, *_args, **_kwargs):
            raise RuntimeError("broker disconnected")

    monkeypatch.setattr("app.actuators.service.mqtt_client", Disconnected())
    with pytest.raises(RuntimeError, match="broker disconnected"):
        publish_actuator_command(db, node_id="AC1", command_type="PHYSICAL_ACTION", payload={"action_category": "BUZZER", "action_type": "ON", "parameters": {}})
    events = db.query(Event).all()
    assert any(event.event_type == "actuator_command_publish_failed" for event in events)
    assert not any(event.event_type == "actuator_command_published" for event in events)


def test_12b_broker_confirmation_timeout_marks_execution_unknown(ack_db, monkeypatch):
    db, _factory, _publisher = ack_db

    class Unconfirmed:
        def publish_confirmed(self, *_args, **_kwargs):
            raise TimeoutError("broker confirmation timeout")

    monkeypatch.setattr("app.actuators.service.mqtt_client", Unconfirmed())
    with pytest.raises(TimeoutError):
        publish_actuator_command(
            db,
            node_id="AC1",
            command_type="PHYSICAL_ACTION",
            payload={"action_category": "BUZZER", "action_type": "ON", "parameters": {}},
        )
    event = next(
        item
        for item in db.query(Event).all()
        if item.event_type == "actuator_command_publish_uncertain"
    )
    projected = get_actuator_status(db).commands[0]
    assert event.payload["device_received"] is None
    assert projected.publish_status == "unknown"
    assert projected.command_state == "execution_unknown"


def test_13_failed_operation_ack_is_failure_not_success(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(command, status="FAILED", stage="failed", reason="OUTPUT_ERROR"))
    result = asyncio.run(wait_for_actuator_ack(command["command_id"], "AC1"))
    assert result.status == "failed"
    assert result.ack_received is True


def test_14_out_of_order_receipt_after_terminal_cannot_regress_state(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(command))
    handlers.handle_ack_message("city/acks/AC1", _ack(command, status="RECEIVED", stage="received"))
    assert len(_accepted_events(db, command["command_id"])) == 1
    projected = get_actuator_status(db).commands[0]
    assert projected.command_state == "execution_reported"


def test_15_stale_ack_for_old_command_does_not_confirm_new_command(ack_db):
    db, _factory, publisher = ack_db
    old = _command(db, publisher)
    new = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(old))
    projection = get_actuator_status(db)
    newest = next(item for item in projection.commands if item.command_id == new["command_id"])
    assert newest.command_state == "waiting_for_ack"
    assert newest.ack_status is None


def test_16_backend_restart_keeps_valid_late_ack_as_audit_state(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    clear_ack_waiter_state()  # models process memory loss while the event store survives
    handlers.handle_ack_message("city/acks/AC1", _ack(command))
    projected = get_actuator_status(db).commands[0]
    assert projected.command_state == "execution_reported"
    assert projected.physical_state_confirmed is False


def test_17_unsupported_action_rejection_does_not_confirm(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher, action="NOT_SUPPORTED")
    handlers.handle_ack_message("city/acks/AC1", _ack(command, status="REJECTED", stage="failed", reason="UNSUPPORTED_ACTION"))
    result = asyncio.run(wait_for_actuator_ack(command["command_id"], "AC1"))
    assert result.status == "failed"
    assert result.ack_payload["reason"] == "UNSUPPORTED_ACTION"


def test_18_simulated_ack_cannot_be_accepted_as_real(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(command, source="simulation", simulated=True))
    assert not _accepted_events(db, command["command_id"])


def test_18b_mock_actuator_refuses_production_topics(monkeypatch):
    from scripts import mock_actuator

    monkeypatch.setattr("sys.argv", ["mock_actuator", "--topic-prefix", "city"])
    with pytest.raises(SystemExit, match="refuses production"):
        mock_actuator.main()


def test_19_ack_action_fields_must_match_command(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(command, action_type="OFF"))
    assert not _accepted_events(db, command["command_id"])


def test_20_dashboard_projection_never_infers_physical_state(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    handlers.handle_ack_message("city/acks/AC1", _ack(command))
    projected = get_actuator_status(db).commands[0]
    assert projected.publish_status == "broker_confirmed"
    assert projected.ack_stage == "execution_reported"
    assert projected.command_state == "execution_reported"
    assert projected.physical_state_confirmed is False


def test_21_isolated_mock_ac1_command_to_dashboard_ack_end_to_end(ack_db):
    db, _factory, publisher = ack_db

    def mock_ac1_publish(topic, payload, *, qos=1):
        assert topic == "city/commands/AC1"
        assert qos == 1
        command = ActuatorCommand.model_validate(payload)
        receipt = _ack(command.model_dump(mode="json"), status="RECEIVED", stage="received")
        execution = _ack(command.model_dump(mode="json"))
        handlers.handle_ack_message("city/acks/AC1", receipt)
        handlers.handle_ack_message("city/acks/AC1", execution)

    publisher.publish_confirmed = mock_ac1_publish
    spec = PhysicalActionCommandSpec(
        action_category=ActionCategory.BUZZER,
        action_type=ActionType.ON,
    )
    result = asyncio.run(
        _execute_normal_with_ack(db, SequencePhase.BUILDING_RESPONSE, spec)
    )
    assert result.status == "acknowledged"
    projected = get_actuator_status(db).commands[0]
    assert projected.publish_status == "broker_confirmed"
    assert projected.ack_stage == "execution_reported"
    assert projected.physical_state_confirmed is False


def test_schema_uses_current_command_contract(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    parsed = ActuatorCommand.model_validate(command)
    assert parsed.command_type == "PHYSICAL_ACTION"


def test_paho_confirmed_publish_waits_for_broker_ack():
    client = MQTTClient()

    class FakeInfo:
        rc = 0

        def __init__(self):
            self.wait_timeout = None

        def wait_for_publish(self, timeout):
            self.wait_timeout = timeout

        def is_published(self):
            return True

    class FakeClient:
        def __init__(self):
            self.info = FakeInfo()
            self.args = None

        def publish(self, topic, payload, qos, retain):
            self.args = (topic, payload, qos, retain)
            return self.info

    fake = FakeClient()
    client._client = fake
    client.publish_confirmed("city/commands/AC1", {"command_id": "test"}, qos=1, timeout=0.4)
    assert fake.args == ("city/commands/AC1", '{"command_id": "test"}', 1, False)
    assert fake.info.wait_timeout == 0.4


def test_same_command_id_cannot_be_reused_for_a_different_action(ack_db):
    db, _factory, publisher = ack_db
    command_id = str(uuid4())
    _command(db, publisher, command_id=command_id, action="ON")
    with pytest.raises(ValueError, match="already assigned"):
        _command(db, publisher, command_id=command_id, action="OFF")


def test_same_id_retry_has_a_separate_audit_event(ack_db):
    db, _factory, publisher = ack_db
    command = _command(db, publisher)
    retry_payload = {
        **command["payload"],
        "attempt_number": 2,
        "retry_of_command_id": command["command_id"],
    }
    publish_actuator_command(
        db,
        node_id="AC1",
        command_type="PHYSICAL_ACTION",
        payload=retry_payload,
        command_id=command["command_id"],
    )
    event_types = [
        event.event_type
        for event in get_events_for_entity(
            db,
            entity_type="command",
            entity_id=command["command_id"],
        )
    ]
    assert event_types.count("actuator_command") == 1
    assert event_types.count("actuator_command_retry") == 1
