"""Read-only latest sensor state derived from immutable events."""

from sqlalchemy.orm import Session

from app.events.repository import get_recent_events
from app.sensors.registry import allowed_sensor_node_ids
from app.sensors.schemas import LatestSensorState, sensor_message_adapter


SUPPORTED_SENSOR_TYPES = ("MQ2", "DHT22", "BUTTON", "IR_A", "IR_B")
SENSOR_PROJECTION_PAGE_SIZE = 100


def get_latest_sensor_states(db: Session) -> list[LatestSensorState]:
    """Build one latest-reading projection per supported sensor type."""

    latest = {
        sensor_type: LatestSensorState(sensor_type=sensor_type)
        for sensor_type in SUPPORTED_SENSOR_TYPES
    }
    allowed_nodes = allowed_sensor_node_ids()

    skip = 0
    while True:
        events = get_recent_events(
            db,
            event_type="sensor_reading",
            limit=SENSOR_PROJECTION_PAGE_SIZE,
            skip=skip,
        )
        for event in events:
            try:
                sensor = sensor_message_adapter.validate_python(event.payload)
            except Exception:
                continue
            if sensor.node_id not in allowed_nodes:
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
                humidity_pct=getattr(sensor, "humidity", None),
                quality=getattr(sensor, "adc_status", None),
                firmware_version=sensor.firmware_version,
                protocol_version=sensor.protocol_version,
                simulated=sensor.simulated,
                available=True,
            )
        if all(state.available for state in latest.values()):
            break
        if len(events) < SENSOR_PROJECTION_PAGE_SIZE:
            break
        skip += SENSOR_PROJECTION_PAGE_SIZE

    return [latest[sensor_type] for sensor_type in SUPPORTED_SENSOR_TYPES]
