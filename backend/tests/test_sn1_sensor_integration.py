"""Isolated SN1 sensor contract, ingestion, freshness, and MQTT tests."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.events.models import Event
from app.events.repository import append_event
from app.fusion.policies import FireSensorNormalizationPolicy
from app.sensors import handlers
from app.sensors.projection import get_latest_sensor_states
from app.sensors.registry import active_sensor_mqtt_topics
from app.sensors.schemas import sensor_message_adapter
from app.vision.schemas import FreshnessItem


def _payload(sensor_type: str = "MQ2", **overrides):
    timestamp = overrides.pop("timestamp", datetime.now(timezone.utc))
    timestamp_text = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    common = {
        "sensor_type": sensor_type,
        "timestamp": timestamp_text,
        "node_id": "SN1",
        "message_id": f"test-{sensor_type}-{timestamp_text}",
        "firmware_version": "sn1-mqtt/1.2.0",
        "protocol_version": "1.1",
    }
    specific = {
        "MQ2": {"value": 500, "unit": "raw", "measurement_kind": "RAW_ADC", "adc_status": "OK"},
        "DHT22": {"value": 25.0, "unit": "C", "humidity": 50.0, "humidity_unit": "pct", "dht_ok": True},
        "BUTTON": {"value": False, "raw": "HIGH"},
        "IR_A": {"value": False, "unit": "blocked", "raw": "HIGH"},
        "IR_B": {"value": False, "unit": "blocked", "raw": "HIGH"},
    }[sensor_type]
    return {**common, **specific, **overrides}


@pytest.fixture
def sensor_db(monkeypatch):
    """Use an in-memory SQLite database and mock fusion/live side effects."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(handlers, "SessionLocal", test_sessions)
    monkeypatch.setattr(
        handlers,
        "get_settings",
        lambda: SimpleNamespace(sensor_mqtt_topic_prefix="test/city/sensors"),
    )
    monkeypatch.setattr(
        "app.sensors.projection.allowed_sensor_node_ids",
        lambda: frozenset({"SN1"}),
    )
    monkeypatch.setattr(handlers, "allowed_sensor_node_ids", lambda: frozenset({"SN1"}))
    monkeypatch.setattr(handlers, "publish_live_update_from_thread", lambda _event: None)
    monkeypatch.setattr(
        handlers,
        "automatic_incident_coordinator",
        SimpleNamespace(observe=lambda _db: None),
    )
    try:
        yield test_sessions
    finally:
        engine.dispose()


def _count_events(session_factory) -> int:
    with session_factory() as db:
        return db.scalar(select(func.count()).select_from(Event)) or 0


def test_active_sensor_subscriptions_are_exact_and_exclude_deferred_topics():
    assert active_sensor_mqtt_topics("/test/city/sensors/") == (
        "test/city/sensors/dht22",
        "test/city/sensors/ir_a",
        "test/city/sensors/ir_b",
    )
    assert active_sensor_mqtt_topics("/") == ()


@pytest.mark.parametrize(
    "sensor_type,value",
    [("MQ2", 500), ("MQ2", 2000), ("DHT22", 25.0), ("DHT22", 45.0),
     ("BUTTON", False), ("IR_A", True), ("IR_B", True)],
)
def test_supported_sensor_contract_accepts_raw_and_elevated_values(sensor_type, value):
    payload = _payload(sensor_type, value=value)
    message = sensor_message_adapter.validate_python(payload)
    assert message.sensor_type == sensor_type
    assert message.value == value


@pytest.mark.parametrize(
    "payload",
    [
        _payload("MQ2", value=-1),
        _payload("MQ2", value=4096),
        _payload("MQ2", value=True),
        _payload("MQ2", value=1200.5),
        _payload("DHT22", value=81.0),
        _payload("DHT22", humidity=100.1),
        _payload("DHT22", value=float("nan")),
        _payload("IR_A", value=1),
        _payload("BUTTON", unit="C"),
        _payload("MQ2", unsupported_sensor_field=123),
        {**_payload("MQ2"), "sensor_type": "UNKNOWN"},
        _payload("MQ2", timestamp="2026-10-26T12:00:00"),
    ],
)
def test_invalid_sensor_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        sensor_message_adapter.validate_python(payload)


def test_sensor_ingestion_checks_topic_identity_allowlist_and_timestamp(sensor_db):
    handlers.handle_sensor_message("city/sensors/mq2", _payload("MQ2"))
    handlers.handle_sensor_message("test/city/sensors/ir_a", _payload("MQ2"))
    handlers.handle_sensor_message("test/city/sensors/mq2", _payload("IR_A"))
    handlers.handle_sensor_message("test/city/sensors/mq2", _payload("MQ2", node_id="UNKNOWN"))
    handlers.handle_sensor_message("test/city/sensors/mq2", "not-json")
    handlers.handle_sensor_message(
        "test/city/sensors/mq2",
        _payload("MQ2", timestamp=datetime.now(timezone.utc) + timedelta(seconds=30)),
    )
    handlers.handle_sensor_message(
        "test/city/sensors/mq2", _payload("MQ2", unsupported_sensor_field="reject")
    )
    assert _count_events(sensor_db) == 0


def test_ingestion_suppresses_duplicate_and_out_of_order_messages(sensor_db):
    first_time = datetime.now(timezone.utc) - timedelta(seconds=2)
    first = _payload("MQ2", timestamp=first_time, message_id="boot-1-1", value=600)
    handlers.handle_sensor_message("test/city/sensors/mq2", first)
    handlers.handle_sensor_message("test/city/sensors/mq2", first)
    handlers.handle_sensor_message(
        "test/city/sensors/mq2",
        _payload("MQ2", timestamp=first_time - timedelta(seconds=1), message_id="boot-1-0"),
    )
    assert _count_events(sensor_db) == 1

    handlers.handle_sensor_message(
        "test/city/sensors/mq2",
        _payload(
            "MQ2",
            timestamp=first_time + timedelta(seconds=3),
            message_id="boot-1-2",
            value=700,
        ),
    )
    assert _count_events(sensor_db) == 2


def test_projection_preserves_humidity_quality_identity_and_simulation_after_restart(sensor_db):
    payload = _payload(
        "DHT22",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
        humidity=63.5,
        simulated=True,
    )
    with sensor_db() as db:
        append_event(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id="SN1",
            payload=payload,
        )

    # Re-open a new session as the backend would after a worker/session restart.
    with sensor_db() as restarted_db:
        dht = next(
            state
            for state in get_latest_sensor_states(restarted_db)
            if state.sensor_type == "DHT22"
        )
    assert dht.available is True
    assert dht.node_id == "SN1"
    assert dht.timestamp == datetime.fromisoformat(payload["timestamp"])
    assert dht.humidity_pct == 63.5
    assert dht.firmware_version == "sn1-mqtt/1.2.0"
    assert dht.protocol_version == "1.1"
    assert dht.simulated is True


def test_sensor_api_serializes_dashboard_contract(sensor_db):
    from fastapi.testclient import TestClient

    from app.auth.dependencies import require_authenticated_role
    from app.core.database import get_db
    from app.main import app

    dht_payload = _payload("DHT22", simulated=True)
    mq2_payload = _payload("MQ2", adc_status="SATURATED", measurement_kind="RAW_ADC")
    handlers.handle_sensor_message("test/city/sensors/dht22", dht_payload)
    handlers.handle_sensor_message("test/city/sensors/mq2", mq2_payload)

    def override_db():
        with sensor_db() as db:
            yield db

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_auth_override = app.dependency_overrides.get(require_authenticated_role)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_authenticated_role] = lambda: SimpleNamespace(id=1)
    try:
        response = TestClient(app).get("/api/sensors/latest")
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        if previous_auth_override is None:
            app.dependency_overrides.pop(require_authenticated_role, None)
        else:
            app.dependency_overrides[require_authenticated_role] = previous_auth_override

    assert response.status_code == 200
    states = {item["sensor_type"]: item for item in response.json()}
    assert states["DHT22"]["unit"] == "C"
    assert states["DHT22"]["humidity_pct"] == 50.0
    assert states["DHT22"]["simulated"] is True
    assert states["DHT22"]["node_id"] == "SN1"
    assert states["DHT22"]["timestamp"] is not None
    assert states["DHT22"]["firmware_version"] == "sn1-mqtt/1.2.0"
    assert states["DHT22"]["protocol_version"] == "1.1"
    assert states["MQ2"]["unit"] == "raw"
    assert states["MQ2"]["quality"] == "SATURATED"
    assert states["MQ2"]["simulated"] is False


def test_projection_ignores_unregistered_historical_sensor_events(sensor_db, monkeypatch):
    payload = _payload("MQ2", node_id="unregistered", value=3000)
    with sensor_db() as db:
        append_event(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id="unregistered",
            payload=payload,
        )
        monkeypatch.setattr(
            "app.sensors.projection.allowed_sensor_node_ids",
            lambda: frozenset({"SN1"}),
        )
        mq2 = next(
            state
            for state in get_latest_sensor_states(db)
            if state.sensor_type == "MQ2"
        )
    assert mq2.available is False


def test_freshness_threshold_marks_ir_offline_and_stale(sensor_db, monkeypatch):
    from app.vision import freshness as freshness_module

    payload = _payload(
        "IR_A",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    with sensor_db() as db:
        append_event(
            db,
            event_type="sensor_reading",
            entity_type="sensor",
            entity_id="SN1",
            payload=payload,
        )
        monkeypatch.setattr(
            freshness_module,
            "get_settings",
            lambda: SimpleNamespace(
                sensor_mq2_stale_after_seconds=2.0,
                sensor_dht22_stale_after_seconds=3.0,
                sensor_digital_stale_after_seconds=2.0,
                vision_stale_after_seconds=1.0,
            ),
        )
        state = freshness_module.get_perception_freshness(db)
    assert state.ir_a.available is True
    assert state.ir_a.stale is True
    assert state.ir_a.age_seconds >= 10.0
    assert state.ir_b.available is False
    assert state.ir_b.stale is None


def test_failed_dht_read_keeps_last_value_stale_then_recovers(sensor_db, monkeypatch):
    from app.vision import freshness as freshness_module

    stale_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
    handlers.handle_sensor_message(
        "test/city/sensors/dht22",
        _payload("DHT22", timestamp=stale_timestamp, value=29.0, humidity=71.0),
    )
    handlers.handle_sensor_message(
        "test/city/sensors/dht22",
        _payload(
            "DHT22",
            timestamp=stale_timestamp + timedelta(seconds=1),
            dht_ok=False,
            value=0.0,
            humidity=0.0,
        ),
    )
    assert _count_events(sensor_db) == 1

    monkeypatch.setattr(
        freshness_module,
        "get_settings",
        lambda: SimpleNamespace(
            sensor_mq2_stale_after_seconds=2.0,
            sensor_dht22_stale_after_seconds=3.0,
            sensor_digital_stale_after_seconds=2.0,
            vision_stale_after_seconds=1.0,
        ),
    )
    with sensor_db() as db:
        state = freshness_module.get_perception_freshness(db)
        previous = next(
            item for item in get_latest_sensor_states(db) if item.sensor_type == "DHT22"
        )
    assert state.dht22.stale is True
    assert previous.value == 29.0
    assert previous.humidity_pct == 71.0

    recovery_timestamp = datetime.now(timezone.utc)
    handlers.handle_sensor_message(
        "test/city/sensors/dht22",
        _payload(
            "DHT22",
            timestamp=recovery_timestamp,
            message_id="dht-recovered",
            value=31.0,
            humidity=68.0,
        ),
    )
    with sensor_db() as db:
        recovered_freshness = freshness_module.get_perception_freshness(db)
        recovered = next(
            item for item in get_latest_sensor_states(db) if item.sensor_type == "DHT22"
        )
    assert recovered_freshness.dht22.stale is False
    assert recovered.value == 31.0
    assert recovered.humidity_pct == 68.0


def test_both_ir_channels_obstruct_and_clear_independently(sensor_db):
    timestamp = datetime.now(timezone.utc)
    for sensor_type in ("IR_A", "IR_B"):
        handlers.handle_sensor_message(
            f"test/city/sensors/{sensor_type.lower()}",
            _payload(sensor_type, timestamp=timestamp, message_id=f"{sensor_type}-blocked", value=True, raw="LOW"),
        )
    with sensor_db() as db:
        blocked = {item.sensor_type: item.value for item in get_latest_sensor_states(db)}
    assert blocked["IR_A"] is True
    assert blocked["IR_B"] is True

    for sensor_type in ("IR_A", "IR_B"):
        handlers.handle_sensor_message(
            f"test/city/sensors/{sensor_type.lower()}",
            _payload(
                sensor_type,
                timestamp=timestamp + timedelta(seconds=1),
                message_id=f"{sensor_type}-clear",
                value=False,
                raw="HIGH",
            ),
        )
    with sensor_db() as db:
        clear = {item.sensor_type: item.value for item in get_latest_sensor_states(db)}
    assert clear["IR_A"] is False
    assert clear["IR_B"] is False


def _fresh(sensor_type: str) -> FreshnessItem:
    return FreshnessItem(
        source_type=sensor_type,
        source_id="SN1",
        available=True,
        stale=False,
        age_seconds=0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    "mq2_value,temp_value,expected",
    [(500, 30.0, 0.0), (2000, 30.0, 1.0), (500, 40.0, 1.0), (2000, 40.0, 1.0)],
)
def test_raw_mq2_and_temperature_fusion_thresholds_remain_provisional_counts(
    mq2_value, temp_value, expected
):
    from app.sensors.schemas import LatestSensorState

    score, status = FireSensorNormalizationPolicy().score_with_freshness(
        LatestSensorState(sensor_type="MQ2", value=mq2_value, unit="raw", available=True),
        LatestSensorState(sensor_type="DHT22", value=temp_value, unit="C", available=True),
        _fresh("MQ2"),
        _fresh("DHT22"),
    )
    assert score == expected
    assert status == "available"


def test_fusion_drops_stale_sensor_and_never_scores_both_stale():
    from app.sensors.schemas import LatestSensorState

    policy = FireSensorNormalizationPolicy()
    mq2 = LatestSensorState(sensor_type="MQ2", value=2000, unit="raw", available=True)
    dht = LatestSensorState(sensor_type="DHT22", value=35.0, unit="C", available=True)
    stale_mq2 = _fresh("MQ2").model_copy(update={"stale": True, "age_seconds": 3.0})
    score, status = policy.score_with_freshness(mq2, dht, stale_mq2, _fresh("DHT22"))
    assert score == 0.5
    assert status == "available"

    stale_dht = _fresh("DHT22").model_copy(update={"stale": True, "age_seconds": 4.0})
    score, status = policy.score_with_freshness(mq2, dht, stale_mq2, stale_dht)
    assert score is None
    assert status == "unavailable"


def test_saturated_mq2_count_is_preserved_but_excluded_from_fusion():
    from app.sensors.schemas import LatestSensorState
    from app.severity.policies import SeverityComponentPolicyProvider
    from app.vision.schemas import PerceptionFreshnessResponse, PerceptionSnapshot

    mq2 = LatestSensorState(
        sensor_type="MQ2",
        value=4095,
        unit="raw",
        quality="SATURATED",
        available=True,
    )
    dht = LatestSensorState(sensor_type="DHT22", value=35.0, unit="C", available=True)
    score, status = FireSensorNormalizationPolicy().score_with_freshness(
        mq2,
        dht,
        _fresh("MQ2"),
        _fresh("DHT22"),
    )
    assert score == 0.5
    assert status == "available"

    timestamp = datetime.now(timezone.utc)
    offline = FreshnessItem(
        source_type="offline",
        source_id=None,
        available=False,
        stale=None,
        age_seconds=None,
        timestamp=None,
    )
    fresh = _fresh("MQ2")
    snapshot = PerceptionSnapshot(
        generated_at=timestamp,
        sensors=[mq2, dht],
        detection=None,
        person_in_hazard=None,
        road_evidence=[],
        freshness=PerceptionFreshnessResponse(
            mq2=fresh,
            dht22=_fresh("DHT22"),
            button=offline,
            ir_a=offline,
            ir_b=offline,
            detection=offline,
            road_evidence=[],
        ),
        road_sync=[],
    )
    severity = SeverityComponentPolicyProvider().provide(snapshot)
    assert severity.s is None
    assert any("saturated" in reason for reason in severity.reasons)


def test_fusion_input_keeps_sensor_source_timestamp_units_quality_and_status():
    from app.fusion.service import build_fusion_input
    from app.sensors.schemas import LatestSensorState
    from app.vision.schemas import PerceptionFreshnessResponse, PerceptionSnapshot

    timestamp = datetime.now(timezone.utc)
    mq2 = LatestSensorState(
        sensor_type="MQ2",
        value=1234,
        timestamp=timestamp,
        node_id="SN1",
        unit="raw",
        quality="OK",
        simulated=True,
        available=True,
    )
    dht = LatestSensorState(
        sensor_type="DHT22",
        value=36.5,
        timestamp=timestamp,
        node_id="SN1",
        unit="C",
        humidity_pct=72.0,
        available=True,
    )

    def available(sensor_type: str) -> FreshnessItem:
        return FreshnessItem(
            source_type=sensor_type,
            source_id="SN1",
            available=True,
            stale=False,
            age_seconds=0,
            timestamp=timestamp,
        )

    def offline(sensor_type: str) -> FreshnessItem:
        return FreshnessItem(
            source_type=sensor_type,
            source_id=None,
            available=False,
            stale=None,
            age_seconds=None,
            timestamp=None,
        )

    snapshot = PerceptionSnapshot(
        generated_at=timestamp,
        sensors=[mq2, dht],
        detection=None,
        person_in_hazard=None,
        road_evidence=[],
        freshness=PerceptionFreshnessResponse(
            mq2=available("MQ2"),
            dht22=available("DHT22"),
            button=offline("BUTTON"),
            ir_a=offline("IR_A"),
            ir_b=offline("IR_B"),
            detection=offline("VISION"),
            road_evidence=[],
        ),
        road_sync=[],
    )

    fusion_input = build_fusion_input(snapshot)
    assert fusion_input.s.mq2 == mq2
    assert fusion_input.s.dht22 == dht
    assert fusion_input.s.mq2.unit == "raw"
    assert fusion_input.s.mq2.quality == "OK"
    assert fusion_input.s.mq2.simulated is True
    assert fusion_input.s.dht22.humidity_pct == 72.0
    assert fusion_input.s.source_references[0].source_id == "SN1"
    assert fusion_input.s.source_references[0].timestamp == timestamp


def test_ir_debounce_resists_noise_and_recovers_after_five_clear_samples():
    from app.routing.state import EdgeState, process_ir_reading

    edge = EdgeState(edge_id="test-only")
    now = datetime.now(timezone.utc)
    for index, blocked in enumerate([True, False, True, False, True]):
        process_ir_reading(edge, blocked, now + timedelta(seconds=index))
    assert edge.ir_state == "OPEN"

    for index in range(5):
        process_ir_reading(edge, True, now + timedelta(seconds=10 + index))
    assert edge.ir_state == "BLOCKED"

    for index in range(5):
        process_ir_reading(edge, False, now + timedelta(seconds=20 + index))
    assert edge.ir_state == "OPEN"


def test_mqtt_transport_reconnects_resubscribes_and_contains_malformed_json(monkeypatch):
    from app.mqtt import client as mqtt_module

    class FakePahoClient:
        def __init__(self):
            self.subscriptions = []
            self.connected = False

        def reconnect_delay_set(self, **_kwargs):
            pass

        def username_pw_set(self, *_args):
            pass

        def is_connected(self):
            return self.connected

        def subscribe(self, topic, qos):
            self.subscriptions.append((topic, qos))
            return 0, 1

    fake = FakePahoClient()
    monkeypatch.setattr(
        mqtt_module,
        "get_settings",
        lambda: SimpleNamespace(
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_username=None,
            mqtt_password=None,
            sensor_mqtt_topic_prefix="test/city/sensors",
        ),
    )
    monkeypatch.setattr(mqtt_module.mqtt, "Client", lambda _version: fake)
    transport = mqtt_module.MQTTClient()
    received = []
    transport.subscribe("test/city/sensors/#", lambda topic, payload: received.append((topic, payload)))
    transport._on_disconnect(fake, None, None, 1, None)
    fake.connected = True
    transport._on_connect(fake, None, {}, 0, None)
    assert transport.is_connected() is True
    assert fake.subscriptions == [("test/city/sensors/#", 1)]

    message = SimpleNamespace(topic="test/city/sensors/mq2", payload=b"{bad-json")
    transport._on_message(fake, None, message)
    assert received == [("test/city/sensors/mq2", "{bad-json")]

    retained = SimpleNamespace(
        topic="test/city/sensors/mq2",
        payload=b'{"sensor_type":"MQ2"}',
        retain=True,
    )
    transport._on_message(fake, None, retained)
    assert len(received) == 1


def test_authenticated_mqtt_broker_to_sensor_state_e2e(sensor_db, monkeypatch, tmp_path):
    """Exercise exact sensor ACLs and backend ingestion on a loopback broker."""
    import paho.mqtt.client as real_mqtt
    from threading import Event, Lock

    mosquitto_candidates = [
        shutil.which("mosquitto"),
        r"C:\Program Files\Mosquitto\mosquitto.exe",
    ]
    mosquitto = next(
        (Path(candidate) for candidate in mosquitto_candidates if candidate and Path(candidate).is_file()),
        None,
    )
    if mosquitto is None:
        pytest.skip("Mosquitto executable is unavailable for the isolated broker test")
    password_tool = mosquitto.with_name("mosquitto_passwd.exe" if os.name == "nt" else "mosquitto_passwd")
    if not password_tool.is_file():
        pytest.skip("Mosquitto password utility is unavailable for the isolated broker test")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        broker_port = probe.getsockname()[1]

    publisher_password = secrets.token_urlsafe(24)
    backend_password = secrets.token_urlsafe(24)
    password_file = tmp_path / "passwords"
    acl_file = tmp_path / "acl"
    log_file = tmp_path / "mosquitto.log"
    config_file = tmp_path / "mosquitto.conf"
    acl_file.write_text(
        "\n".join(
            [
                "user sn1_test_publisher",
                "topic write city/sensors/dht22",
                "topic write city/sensors/ir_a",
                "topic write city/sensors/ir_b",
                "user backend_test_reader",
                "topic read city/sensors/dht22",
                "topic read city/sensors/ir_a",
                "topic read city/sensors/ir_b",
                "",
            ]
        ),
        encoding="utf-8",
    )
    first_password = subprocess.run(
        [str(password_tool), "-b", "-c", str(password_file), "sn1_test_publisher", publisher_password],
        capture_output=True,
        text=True,
        check=False,
    )
    second_password = subprocess.run(
        [str(password_tool), "-b", str(password_file), "backend_test_reader", backend_password],
        capture_output=True,
        text=True,
        check=False,
    )
    assert first_password.returncode == 0, "Unable to prepare isolated publisher credentials"
    assert second_password.returncode == 0, "Unable to prepare isolated backend credentials"

    config_file.write_text(
        "\n".join(
            [
                f"listener {broker_port} 127.0.0.1",
                "allow_anonymous false",
                f"password_file {password_file.as_posix()}",
                f"acl_file {acl_file.as_posix()}",
                "persistence false",
                f"log_dest file {log_file.as_posix()}",
                "log_type all",
                "",
            ]
        ),
        encoding="utf-8",
    )
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    broker = subprocess.Popen(
        [str(mosquitto), "-c", str(config_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=no_window,
    )

    from app.mqtt import client as mqtt_module

    settings = SimpleNamespace(
        mqtt_host="127.0.0.1",
        mqtt_port=broker_port,
        mqtt_username="backend_test_reader",
        mqtt_password=backend_password,
        sensor_mqtt_topic_prefix="city/sensors",
    )
    monkeypatch.setattr(mqtt_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        handlers,
        "get_settings",
        lambda: SimpleNamespace(sensor_mqtt_topic_prefix="city/sensors"),
    )
    transport = mqtt_module.MQTTClient()
    topics = active_sensor_mqtt_topics(settings.sensor_mqtt_topic_prefix)
    callbacks_complete = Event()
    completed_topics = set()
    completed_topics_lock = Lock()

    def ingest_and_signal(topic, payload):
        handlers.handle_sensor_message(topic, payload)
        with completed_topics_lock:
            completed_topics.add(topic)
            if set(topics).issubset(completed_topics):
                callbacks_complete.set()

    for topic in topics:
        transport.subscribe(topic, ingest_and_signal)

    publisher = real_mqtt.Client(
        real_mqtt.CallbackAPIVersion.VERSION2,
        client_id="SN1-isolated-test-publisher",
    )
    publisher.username_pw_set("sn1_test_publisher", publisher_password)
    try:
        transport.start()
        assert transport.wait_until_connected(5), "Backend MQTT client did not authenticate to loopback broker"
        publisher.connect("127.0.0.1", broker_port, keepalive=10)
        publisher.loop_start()

        while_deadline = time.monotonic() + 5
        while not publisher.is_connected() and time.monotonic() < while_deadline:
            time.sleep(0.02)
        assert publisher.is_connected(), "SN1 test publisher did not authenticate to loopback broker"

        measurements = (
            ("city/sensors/dht22", _payload("DHT22", value=31.8, humidity=73.8)),
            ("city/sensors/ir_a", _payload("IR_A", value=True, raw="LOW")),
            ("city/sensors/ir_b", _payload("IR_B", value=False, raw="HIGH")),
        )
        for topic, payload in measurements:
            info = publisher.publish(topic, json.dumps(payload), qos=0, retain=False)
            assert info.rc == real_mqtt.MQTT_ERR_SUCCESS

        assert callbacks_complete.wait(5), "Backend sensor callbacks did not finish in time"
        assert _count_events(sensor_db) == len(measurements)

        # The same SN1 principal must be denied MQ2, button, and actuator topics.
        for topic in (
            "city/sensors/mq2",
            "city/sensors/button",
            "city/commands/AC1",
        ):
            info = publisher.publish(topic, "{}", qos=0, retain=False)
            assert info.rc == real_mqtt.MQTT_ERR_SUCCESS

        deny_deadline = time.monotonic() + 3
        denied_topics = set()
        while time.monotonic() < deny_deadline:
            if log_file.exists():
                log_text = log_file.read_text(encoding="utf-8", errors="replace")
                denied_topics = {
                    topic
                    for topic in ("city/sensors/mq2", "city/sensors/button", "city/commands/AC1")
                    if "Denied PUBLISH" in log_text and topic in log_text
                }
                if len(denied_topics) == 3:
                    break
            time.sleep(0.05)
        assert denied_topics == {
            "city/sensors/mq2",
            "city/sensors/button",
            "city/commands/AC1",
        }
        assert _count_events(sensor_db) == len(measurements)

        with sensor_db() as db:
            latest = {item.sensor_type: item for item in get_latest_sensor_states(db)}
        assert latest["DHT22"].value == 31.8
        assert latest["DHT22"].humidity_pct == 73.8
        assert latest["DHT22"].firmware_version == "sn1-mqtt/1.2.0"
        assert latest["IR_A"].value is True
        assert latest["IR_B"].value is False
        assert latest["MQ2"].available is False
        assert latest["BUTTON"].available is False
    finally:
        publisher.loop_stop()
        publisher.disconnect()
        transport.stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
            broker.wait(timeout=5)
