"""Lightweight observational system health service."""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.events.repository import get_recent_events
from app.live.manager import live_connection_manager
from app.mqtt.client import mqtt_client
from app.vision.runtime import vision_runtime_health
from app.vision.live import shared_vision_frames


class SystemComponentStatus(BaseModel):
    status: str
    last_seen: datetime | None = None
    detail: str | None = None
    connected_clients: int | None = None


class SystemHealthResponse(BaseModel):
    backend: SystemComponentStatus
    database: SystemComponentStatus
    mqtt: SystemComponentStatus
    websocket: SystemComponentStatus
    sensor_activity: SystemComponentStatus
    actuator_ack_activity: SystemComponentStatus
    vision: SystemComponentStatus


def _activity_status(db: Session, *, event_type: str, label: str) -> SystemComponentStatus:
    events = get_recent_events(db, event_type=event_type, limit=1)
    if not events:
        return SystemComponentStatus(
            status="unknown",
            detail=f"No {label} events recorded",
        )

    event = events[0]
    sensor_type = event.payload.get("sensor_type")
    detail = f"Latest {label} event"
    if sensor_type:
        detail = f"Latest {label} event: {sensor_type}"
    return SystemComponentStatus(
        status="available",
        last_seen=event.created_at,
        detail=detail,
    )


def get_system_health(db: Session) -> SystemHealthResponse:
    """Collect current observational status without mutating application state."""

    try:
        db.execute(text("SELECT 1"))
        database = SystemComponentStatus(status="healthy", detail="SQLite query succeeded")
    except SQLAlchemyError:
        database = SystemComponentStatus(status="unavailable", detail="SQLite query failed")

    connected_clients = live_connection_manager.connected_count()
    websocket = SystemComponentStatus(
        status="connected" if connected_clients else "available",
        detail="Live clients connected" if connected_clients else "No live clients connected",
        connected_clients=connected_clients,
    )
    mqtt_connected = mqtt_client.is_connected()
    mqtt = SystemComponentStatus(
        status="connected" if mqtt_connected else "unavailable",
        detail="MQTT broker connection ready"
        if mqtt_connected
        else "MQTT broker connection not ready",
    )

    vision_runtime = vision_runtime_health.snapshot()
    live_state, live_error = shared_vision_frames.status()
    if live_state == "initializing" and vision_runtime.status != "available":
        vision_status = SystemComponentStatus(
            status="warming",
            last_seen=vision_runtime.last_seen,
            detail="Shared AI camera pipeline is initializing",
        )
    elif live_state == "error":
        vision_status = SystemComponentStatus(
            status="unavailable",
            last_seen=vision_runtime.last_seen,
            detail=live_error or vision_runtime.detail,
        )
    else:
        vision_status = SystemComponentStatus(
            status=vision_runtime.status,
            last_seen=vision_runtime.last_seen,
            detail=vision_runtime.detail,
        )

    return SystemHealthResponse(
        backend=SystemComponentStatus(status="healthy", detail="Backend is running"),
        database=database,
        mqtt=mqtt,
        websocket=websocket,
        sensor_activity=_activity_status(db, event_type="sensor_reading", label="sensor"),
        actuator_ack_activity=_activity_status(
            db,
            event_type="actuator_ack",
            label="actuator ACK",
        ),
        vision=vision_status,
    )
