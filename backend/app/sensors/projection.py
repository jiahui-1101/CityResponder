"""Read-only latest sensor state derived from immutable events."""

from sqlalchemy.orm import Session

from app.events.repository import get_recent_events
from app.sensors.schemas import LatestSensorState, sensor_message_adapter


SUPPORTED_SENSOR_TYPES = ("MQ2", "DHT22", "BUTTON", "IR_A", "IR_B")


def get_latest_sensor_states(db: Session) -> list[LatestSensorState]:
    """Build one latest-reading projection per supported sensor type."""

    latest = {
        sensor_type: LatestSensorState(sensor_type=sensor_type)
        for sensor_type in SUPPORTED_SENSOR_TYPES
    }

    for event in get_recent_events(db, event_type="sensor_reading"):
        try:
            sensor = sensor_message_adapter.validate_python(event.payload)
        except Exception:
            continue

        state = latest[sensor.sensor_type]
        if state.available:
            continue

        latest[sensor.sensor_type] = LatestSensorState(
            sensor_type=sensor.sensor_type,
            value=event.payload.get("value"),
            timestamp=sensor.timestamp,
            node_id=sensor.node_id,
            unit=event.payload.get("unit"),
            available=True,
        )

    return [latest[sensor_type] for sensor_type in SUPPORTED_SENSOR_TYPES]
