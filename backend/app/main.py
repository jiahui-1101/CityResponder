"""FastAPI application entry point for CityResponder."""

import asyncio
from contextlib import asynccontextmanager

from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth.admin_router import router as admin_router
from app.auth.dependencies import authenticate_token, require_any_role, require_authenticated_role
from app.auth.models import User, UserRole
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
from app.area_risk.router import router as area_risk_router
from app.calibration.router import router as calibration_router
from app.evidence.router import router as evidence_router
from app.lifecycle.router import router as lifecycle_router
from app.inspections.router import router as inspections_router
from app.severity.router import router as severity_router
from app.vision.handlers import handle_detection_message, handle_road_message
from app.vision.live import shared_vision_frames
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
    # Warm the one shared camera/model pipeline in its daemon worker. API
    # startup stays responsive and concurrent browser requests cannot create a
    # second camera or model initialization.
    shared_vision_frames.start()
    try:
        yield
    finally:
        shared_vision_frames.stop()
        mqtt_client.stop()
        clear_live_event_loop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-CityResponder-Frame-Id",
        "X-CityResponder-Frame-Timestamp",
        "X-CityResponder-Detection-Model",
        "X-CityResponder-Segmentation-Model",
        "X-CityResponder-Detection-Count",
        "X-CityResponder-Segmentation-Count",
        "ETag",
    ],
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(severity_router)
app.include_router(routing_router)
app.include_router(area_risk_router)
app.include_router(calibration_router)
app.include_router(evidence_router)
app.include_router(lifecycle_router)
app.include_router(inspections_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a lightweight liveness response."""

    return {"status": "healthy"}


@app.get("/api/events", response_model=list[EventRead])
def list_events(
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_authenticated_role),
) -> list[EventRead]:
    """Return recent immutable events without mutating the event store."""

    return get_recent_events(db, limit=limit, event_type=event_type, entity_type=entity_type, entity_id=entity_id, start_at=start_at, end_at=end_at, skip=skip)


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


@app.get("/api/vision/live-frame")
def live_annotated_vision_frame(
    if_none_match: str | None = Header(default=None),
    _current_user: User = Depends(
        require_any_role(UserRole.OPERATOR, UserRole.FIREFIGHTER)
    ),
) -> Response:
    """Return the latest shared annotated frame without persisting video."""

    try:
        frame = shared_vision_frames.latest()
    except TimeoutError as exc:
        state, _detail = shared_vision_frames.status()
        raise HTTPException(
            status_code=503,
            detail="Camera warming up" if state == "initializing" else str(exc),
            headers={"Retry-After": "2"},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    etag = f'"{frame.sequence}"'
    if if_none_match == etag:
        return Response(status_code=304, headers={"Cache-Control": "no-store", "ETag": etag})
    metadata = frame.metadata
    return Response(
        content=frame.jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "ETag": etag,
            "X-CityResponder-Frame-Id": str(metadata.get("frame_id", "")),
            "X-CityResponder-Frame-Timestamp": str(metadata.get("timestamp", "")),
            "X-CityResponder-Detection-Model": str(
                metadata.get("detection_model", {}).get("version", "unknown")
            ),
            "X-CityResponder-Segmentation-Model": str(
                metadata.get("segmentation_model", {}).get("version", "unknown")
            ),
            "X-CityResponder-Detection-Count": str(len(metadata.get("detections", []))),
            "X-CityResponder-Segmentation-Count": str(len(metadata.get("segmentations", []))),
        },
    )


@app.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    """Keep an authenticated client connected to receive live updates."""

    await websocket.accept()
    db = SessionLocal()
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if not isinstance(message, dict):
            raise HTTPException(status_code=401, detail="Missing access token")
        token = message.get("token")
        if message.get("type") != "authenticate" or not isinstance(token, str):
            raise HTTPException(status_code=401, detail="Missing access token")
        current_user = authenticate_token(token, db)
    except (HTTPException, asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return
    finally:
        db.close()

    await live_connection_manager.connect(
        websocket,
        user_id=current_user.id,
        role=current_user.role.value,
        already_accepted=True,
    )
    await websocket.send_json(
        {
            "event_type": "connection_authenticated",
            "payload": {"status": "connected"},
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live_connection_manager.disconnect(websocket)
    except Exception:
        live_connection_manager.disconnect(websocket)
