"""FastAPI application entry point for CityResponder."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.admin_router import router as admin_router
from app.auth.dependencies import authenticate_token, require_authenticated_role
from app.auth.models import User
from app.auth.router import router as auth_router
from app.auth.service import seed_development_users
from app.actuators.handlers import handle_ack_message
from app.actuators.projection import get_actuator_status
from app.actuators.schemas import ActuatorStatusResponse
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db, initialize_database
from app.core.logging import configure_logging
from app.events.repository import get_events_for_entity, get_recent_events
from app.events.schemas import EventRead
from app.live.manager import live_connection_manager
from app.live.service import clear_live_event_loop, set_live_event_loop
from app.mqtt.client import mqtt_client
from app.sensors.handlers import handle_sensor_message
from app.sensors.projection import get_latest_sensor_states
from app.sensors.schemas import LatestSensorState
from app.system.health import SystemHealthResponse, get_system_health
from app.routing.router import router as routing_router
from app.severity.router import router as severity_router
from app.vision.handlers import handle_detection_message, handle_road_message
from app.vision.freshness import get_perception_freshness
from app.vision.projection import get_latest_vision_state
from app.vision.schemas import (
    LatestVisionResponse,
    PerceptionFreshnessResponse,
    PerceptionSnapshot,
    RoadIRSyncEvidence,
)
from app.vision.snapshot import get_perception_snapshot
from app.vision.sync import get_road_ir_sync


settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize foundational resources when the application starts."""

    initialize_database()
    seed_development_users()
    set_live_event_loop(asyncio.get_running_loop())
    mqtt_client.subscribe("city/sensors/#", handle_sensor_message)
    mqtt_client.subscribe("city/vision/detection", handle_detection_message)
    mqtt_client.subscribe("city/vision/road", handle_road_message)
    mqtt_client.subscribe("city/acks/#", handle_ack_message)
    mqtt_client.start()
    try:
        yield
    finally:
        mqtt_client.stop()
        clear_live_event_loop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(severity_router)
app.include_router(routing_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a lightweight liveness response."""

    return {"status": "healthy"}


@app.get("/api/events", response_model=list[EventRead])
def list_events(
    event_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> list[EventRead]:
    """Return recent immutable events without mutating the event store."""

    return get_recent_events(db, limit=limit, event_type=event_type)


@app.get("/api/events/{entity_type}/{entity_id}", response_model=list[EventRead])
def list_entity_events(
    entity_type: str,
    entity_id: str,
    event_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> list[EventRead]:
    """Return recent immutable events for one entity."""

    return get_events_for_entity(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
    )


@app.get("/api/sensors/latest", response_model=list[LatestSensorState])
def latest_sensors(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> list[LatestSensorState]:
    """Return the latest raw reading projection for each sensor type."""

    return get_latest_sensor_states(db)


@app.get("/api/actuators/status", response_model=ActuatorStatusResponse)
def actuator_status(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> ActuatorStatusResponse:
    """Return recent command/ACK projections and AC1 status."""

    return get_actuator_status(db)


@app.get("/api/system/health", response_model=SystemHealthResponse)
def system_health(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> SystemHealthResponse:
    """Return observational health for current backend components."""

    return get_system_health(db)


@app.get("/api/vision/latest", response_model=LatestVisionResponse)
def latest_vision(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> LatestVisionResponse:
    """Return the latest read-only vision projection from immutable events."""

    return get_latest_vision_state(db)


@app.get("/api/perception/freshness", response_model=PerceptionFreshnessResponse)
def perception_freshness(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> PerceptionFreshnessResponse:
    """Return read-only freshness evaluation for sensors and vision sources."""

    return get_perception_freshness(db)


@app.get("/api/perception/road-sync", response_model=list[RoadIRSyncEvidence])
def road_ir_sync(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> list[RoadIRSyncEvidence]:
    """Return read-only camera/IR synchronization evidence per road ROI."""

    return get_road_ir_sync(db)


@app.get("/api/perception/snapshot", response_model=PerceptionSnapshot)
def perception_snapshot(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> PerceptionSnapshot:
    """Return a read-only combined perception snapshot."""

    return get_perception_snapshot(db)


@app.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    """Keep an authenticated client connected to receive live updates."""

    token = websocket.query_params.get("token")
    db = SessionLocal()
    try:
        if not token:
            raise HTTPException(status_code=401, detail="Missing access token")
        current_user = authenticate_token(token, db)
    except HTTPException:
        await websocket.accept()
        await websocket.close(code=1008)
        return
    finally:
        db.close()

    await live_connection_manager.connect(
        websocket,
        user_id=current_user.id,
        role=current_user.role.value,
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live_connection_manager.disconnect(websocket)
    except Exception:
        live_connection_manager.disconnect(websocket)
