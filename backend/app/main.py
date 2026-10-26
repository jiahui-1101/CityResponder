"""FastAPI application entry point for CityResponder."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timezone
from threading import BoundedSemaphore
import time

from datetime import datetime

import jwt
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
from app.sensors.registry import active_sensor_mqtt_topics
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
from app.vision.preview import CameraPreviewUnavailable, shared_camera_preview
from app.vision.inference_display import (
    AIFramePresentationPolicy,
    VisionDisplayUnavailable,
    shared_vision_display,
)
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
logger = logging.getLogger(__name__)
_VISION_STREAM_SLOTS = BoundedSemaphore(4)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize foundational resources when the application starts."""

    initialize_database()
    if settings.environment.strip().lower() in {"development", "dev", "test"}:
        seed_development_users()
    else:
        logger.info("Development account seeding disabled outside development")
    set_live_event_loop(asyncio.get_running_loop())
    for sensor_topic in active_sensor_mqtt_topics(settings.sensor_mqtt_topic_prefix):
        mqtt_client.subscribe(sensor_topic, handle_sensor_message)
    mqtt_client.subscribe("city/vision/detection", handle_detection_message)
    mqtt_client.subscribe("city/vision/road", handle_road_message)
    mqtt_client.subscribe("city/acks/#", handle_ack_message)
    mqtt_client.start()
    # Live inference stays opt-in. This keeps REST/dashboard startup usable
    # while camera mode or ROI geometry is being validated locally.
    if settings.vision_live_enabled:
        logger.info(
            "Starting shared vision worker; evidence_publishing_enabled=%s",
            settings.vision_publish_evidence_enabled,
        )
        shared_vision_frames.start()
    else:
        logger.info("Shared vision worker disabled by VISION_LIVE_ENABLED=false")
    try:
        yield
    finally:
        shared_vision_display.stop()
        shared_camera_preview.stop()
        shared_vision_frames.stop()
        mqtt_client.stop()
        clear_live_event_loop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.environment.strip().lower() in {"development", "dev", "test"} else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment.strip().lower() in {"development", "dev", "test"} else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    # The frontend stores bearer tokens in localStorage; cookie credentials
    # and wildcard methods/headers are not needed.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "If-None-Match"],
    expose_headers=[
        "X-CityResponder-Frame-Id",
        "X-CityResponder-Frame-Timestamp",
        "X-CityResponder-Frame-Mode",
        "X-CityResponder-Capture-Width",
        "X-CityResponder-Capture-Height",
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
    """Return a camera-only JPEG or, separately, an opted-in annotated frame."""

    if settings.vision_preview_enabled:
        try:
            preview = shared_camera_preview.latest()
        except TimeoutError as exc:
            raise HTTPException(
                status_code=503,
                detail="Camera initializing",
                headers={"Retry-After": "1"},
            ) from exc
        except CameraPreviewUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc),
                headers={"Retry-After": "2"},
            ) from exc
        etag = f'"{preview.frame_id}"'
        headers = {
            "Cache-Control": "no-store",
            "ETag": etag,
            "X-CityResponder-Frame-Mode": "camera-only",
            "X-CityResponder-Frame-Id": preview.frame_id,
            "X-CityResponder-Frame-Timestamp": preview.timestamp.isoformat(),
            "X-CityResponder-Capture-Width": str(preview.capture_width),
            "X-CityResponder-Capture-Height": str(preview.capture_height),
        }
        if if_none_match == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=preview.jpeg, media_type="image/jpeg", headers=headers)

    if not settings.vision_live_enabled:
        raise HTTPException(
            status_code=503,
            detail="Live vision is disabled (set VISION_LIVE_ENABLED=true to enable it)",
        )
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

    origin = websocket.headers.get("origin")
    allowed_origins = {
        item.strip()
        for item in settings.cors_allowed_origins.split(",")
        if item.strip()
    }
    allowed_origins.update(
        item.strip()
        for item in settings.websocket_allowed_origins.split(",")
        if item.strip()
    )
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008)
        return

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
        channel = message.get("channel")
        if channel == "vision":
            if not origin or origin not in allowed_origins:
                await websocket.close(code=1008)
                return
            if current_user.role not in {
                UserRole.OPERATOR,
                UserRole.FIREFIGHTER,
                UserRole.ADMIN,
            }:
                await websocket.close(code=1008)
                return
            if not settings.vision_preview_enabled:
                await websocket.send_json(
                    {"event_type": "vision_status", "payload": {"error": "Camera preview is disabled"}}
                )
                await websocket.close(code=1013)
                return
            claims = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            expires_at = float(claims["exp"])
            view = message.get("view", "ai")
            if view not in {"ai", "raw"}:
                await websocket.close(code=1008)
                return
            db.close()
            await _stream_observation_frames(websocket, view=view, expires_at=expires_at)
            return
    except (
        HTTPException,
        asyncio.TimeoutError,
        ValueError,
        jwt.InvalidTokenError,
        WebSocketDisconnect,
    ):
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


async def _stream_observation_frames(
    websocket: WebSocket,
    *,
    view: str,
    expires_at: float,
) -> None:
    """Stream latest raw or matching AI JPEGs over one JWT-authenticated socket."""

    if not _VISION_STREAM_SLOTS.acquire(blocking=False):
        await websocket.close(code=1013)
        return

    raw_sequence = -1
    ai_sequence = -1
    presentation = AIFramePresentationPolicy(settings.vision_ai_overlay_valid_seconds)
    last_status_at = 0.0

    async def send_status(payload: dict, *, interval_seconds: float = 1.0) -> None:
        """Rate-limit status-only traffic while preserving frame delivery."""

        nonlocal last_status_at
        now = time.time()
        if now - last_status_at < interval_seconds:
            return
        last_status_at = now
        await websocket.send_json({"event_type": "vision_stream_status", "payload": payload})
    try:
        await websocket.send_json(
            {
                "event_type": "vision_stream_authenticated",
                "payload": {"status": "connected", "view": view},
            }
        )
        if view == "ai" and settings.vision_ai_display_enabled:
            shared_vision_display.start()

        while True:
            if time.time() >= expires_at:
                await websocket.close(code=1008)
                return

            if view == "raw" or not settings.vision_ai_display_enabled:
                try:
                    frame = await asyncio.to_thread(
                        shared_camera_preview.latest,
                        timeout_seconds=0.75,
                        after_sequence=raw_sequence,
                    )
                except TimeoutError:
                    await send_status({"camera_status": shared_camera_preview.status()})
                    continue
                raw_sequence = frame.sequence
                output_view = view if view == "raw" else "raw-fallback"
                await websocket.send_json(_raw_stream_payload(frame, view=output_view))
                await websocket.send_bytes(frame.jpeg)
                continue

            try:
                frame = await asyncio.to_thread(
                    shared_vision_display.latest,
                    timeout_seconds=0.35,
                    after_sequence=ai_sequence,
                )
                geometry_version = _crop_geometry_version(frame)
                if not presentation.accept_ai(
                    sequence=frame.sequence,
                    frame_id=frame.frame_id,
                    timestamp=frame.timestamp,
                    geometry_version=geometry_version,
                ):
                    await send_status(
                        {
                            "camera_status": shared_camera_preview.status(),
                            "inference": shared_vision_display.status(),
                            "overlay_state": presentation.overlay_state(),
                            "discarded_ai_frame": "stale_or_out_of_order",
                        }
                    )
                    continue
                ai_sequence = frame.sequence
                await websocket.send_json(_ai_stream_payload(frame))
                await websocket.send_bytes(frame.jpeg)
            except (TimeoutError, VisionDisplayUnavailable):
                # Raw imagery is useful only while the first AI frame warms up.
                # After that, retaining the last synchronized AI JPEG avoids
                # alternating annotated and unannotated frames. Status updates
                # still expose stale/error state without claiming new inference.
                if not presentation.allow_raw_fallback():
                    status = shared_vision_display.status()
                    await send_status(
                        {
                            "camera_status": shared_camera_preview.status(),
                            "inference": status,
                            "overlay_state": presentation.overlay_state(),
                        }
                    )
                    continue
                try:
                    frame = await asyncio.to_thread(
                        shared_camera_preview.latest,
                        timeout_seconds=0.25,
                        after_sequence=raw_sequence,
                    )
                except TimeoutError:
                    await send_status(
                        {
                            "camera_status": shared_camera_preview.status(),
                            "inference": shared_vision_display.status(),
                        }
                    )
                    continue
                raw_sequence = frame.sequence
                status = shared_vision_display.status()
                payload = _raw_stream_payload(frame, view="raw-fallback")
                payload["payload"].update(
                    {
                        "detection_status": status["detection"],
                        "segmentation_status": status["segmentation"],
                        "inference_error": status["error"],
                    }
                )
                await websocket.send_json(payload)
                await websocket.send_bytes(frame.jpeg)

            if time.time() - last_status_at >= 5.0:
                await send_status(
                    {
                        "camera_status": shared_camera_preview.status(),
                        "inference": shared_vision_display.status(),
                        "overlay_state": presentation.overlay_state(),
                        "roi_status": "unverified",
                        "roi_overlay": "not_drawn",
                    },
                    interval_seconds=5.0,
                )
    except (WebSocketDisconnect, CameraPreviewUnavailable):
        return
    finally:
        _VISION_STREAM_SLOTS.release()


def _raw_stream_payload(frame, *, view: str) -> dict:
    performance = shared_camera_preview.performance_snapshot()
    inference = (
        shared_vision_display.status()
        if settings.vision_ai_display_enabled
        else {"detection": "disabled", "segmentation": "disabled", "error": None}
    )
    age_ms = max(
        0.0,
        (datetime.now(timezone.utc) - frame.timestamp).total_seconds() * 1000,
    )
    return {
        "event_type": "vision_frame",
        "payload": {
            "view": view,
            "sequence": frame.sequence,
            "frame_id": frame.frame_id,
            "timestamp": frame.timestamp.isoformat(),
            "frame_age_ms": age_ms,
            "capture_width": frame.capture_width,
            "capture_height": frame.capture_height,
            "source_width": frame.source_width,
            "source_height": frame.source_height,
            "crop_origin_x": frame.crop_origin_x,
            "crop_origin_y": frame.crop_origin_y,
            "crop_right_x": frame.crop_right_x,
            "crop_bottom_y": frame.crop_bottom_y,
            "crop_geometry_version": _crop_geometry_version(frame),
            "preview_width": frame.preview_width,
            "preview_height": frame.preview_height,
            "camera_fps": frame.camera_fps or performance["capture_fps"],
            "capture_latency_ms": frame.capture_latency_ms,
            "resize_latency_ms": frame.resize_latency_ms,
            "jpeg_encode_ms": frame.jpeg_encode_ms,
            "jpeg_bytes": len(frame.jpeg),
            "detection_status": inference["detection"],
            "segmentation_status": inference["segmentation"],
            "detection_fps": 0.0,
            "segmentation_fps": 0.0,
            "detection_latency_ms": None,
            "segmentation_latency_ms": None,
            "inference_device": inference.get("inference_device", "unavailable"),
            "detections": [],
            "segmentations": [],
            "roi_status": "unverified",
            "roi_overlay": "not_drawn",
        },
    }


def _ai_stream_payload(frame) -> dict:
    age_ms = max(
        0.0,
        (datetime.now(timezone.utc) - frame.timestamp).total_seconds() * 1000,
    )
    from app.vision.shadow import evaluate_live_shadow
    shadow = evaluate_live_shadow(
        frame_id=frame.frame_id,
        timestamp=frame.timestamp,
        processed_at=frame.processed_at,
        crop_geometry_version=_crop_geometry_version(frame),
        detections=list(frame.detections),
        segmentations=list(frame.segmentations),
    )
    return {
        "event_type": "vision_frame",
        "payload": {
            "view": "ai-overlay",
            "sequence": frame.sequence,
            "frame_id": frame.frame_id,
            "inference_source_frame_id": frame.frame_id,
            "timestamp": frame.timestamp.isoformat(),
            "processed_at": frame.processed_at.isoformat(),
            "frame_age_ms": age_ms,
            "capture_width": frame.capture_width,
            "capture_height": frame.capture_height,
            "source_width": frame.source_width,
            "source_height": frame.source_height,
            "crop_origin_x": frame.crop_origin_x,
            "crop_origin_y": frame.crop_origin_y,
            "crop_right_x": frame.crop_right_x,
            "crop_bottom_y": frame.crop_bottom_y,
            "crop_geometry_version": _crop_geometry_version(frame),
            "preview_width": frame.preview_width,
            "preview_height": frame.preview_height,
            "camera_fps": frame.camera_fps,
            "detection_status": frame.detection_status,
            "segmentation_status": frame.segmentation_status,
            "detection_fps": frame.detection_fps,
            "segmentation_fps": frame.segmentation_fps,
            "detection_latency_ms": frame.detection_latency_ms,
            "segmentation_latency_ms": frame.segmentation_latency_ms,
            "inference_latency_ms": frame.inference_latency_ms,
            "inference_device": frame.inference_device,
            "jpeg_bytes": len(frame.jpeg),
            "detections": list(frame.detections),
            "segmentations": list(frame.segmentations),
            "roi_status": "unverified",
            "roi_overlay": "not_drawn",
            "shadow_evaluation": shadow.model_dump(mode="json"),
        },
    }


def _crop_geometry_version(frame) -> str:
    """Stable display geometry identity used to reject incompatible overlays."""

    return (
        f"{frame.source_width}x{frame.source_height}:"
        f"{frame.crop_origin_x},{frame.crop_origin_y}-"
        f"{frame.crop_right_x},{frame.crop_bottom_y}:"
        f"{frame.capture_width}x{frame.capture_height}"
    )
