"""Append-only lifecycle transitions for responder and operator workflows."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth.models import User
from app.events.models import Event
from app.events.repository import append_event, get_events_for_entity
from app.events.schemas import EventRead
from app.lifecycle.schemas import (
    OperatorFeedbackRequest,
    OperatorLifecycleRequest,
    PreliminaryOutcome,
    ResponderActionRequest,
    ResponseLifecycleProjection,
)
from app.live.service import publish_live_update_from_thread

INCIDENT = "incident"
LIFECYCLE_EVENT = "responder_lifecycle"
OPERATOR_EVENT = "operator_lifecycle"
FEEDBACK_EVENT = "operator_feedback"


def _events(db: Session, incident_id: str) -> list[Event]:
    return sorted(
        get_events_for_entity(db, entity_type=INCIDENT, entity_id=incident_id),
        key=lambda event: (event.created_at, event.id),
    )


def _ensure_incident(events: list[Event], incident_id: str) -> None:
    if not any(event.event_type == "incident_decision" for event in events):
        raise LookupError(f"incident {incident_id} not found")


def get_lifecycle(db: Session, incident_id: str) -> ResponseLifecycleProjection | None:
    events = _events(db, incident_id)
    if not any(event.event_type == "incident_decision" for event in events):
        return None
    status = "DISPATCHED"
    changed_at = None
    preliminary = None
    probable_cause = None
    inspection_required = None
    notes = None
    verified = None
    for event in events:
        if event.event_type in {LIFECYCLE_EVENT, OPERATOR_EVENT}:
            status = str(event.payload.get("status", status))
            changed_at = event.created_at
        if event.event_type == LIFECYCLE_EVENT:
            preliminary = event.payload.get("preliminary_outcome", preliminary)
            probable_cause = event.payload.get("probable_cause", probable_cause)
            inspection_required = event.payload.get("inspection_required", inspection_required)
            notes = event.payload.get("notes", notes)
        if event.event_type == FEEDBACK_EVENT:
            verified = event.payload.get("outcome", verified)
            status = "VERIFIED" if verified == "VERIFIED_FALSE_ALARM" else "VERIFIED_FIRE"
            changed_at = event.created_at
    return ResponseLifecycleProjection(
        incident_id=incident_id,
        status=status,
        status_changed_at=changed_at,
        preliminary_outcome=preliminary,
        probable_cause=probable_cause,
        inspection_required=inspection_required,
        notes=notes,
        verified_outcome=verified,
        events=[EventRead.model_validate(event) for event in events],
    )


def _publish(event: Event, payload: dict, event_type: str, incident_id: str) -> None:
    publish_live_update_from_thread({
        "event_type": event_type,
        "event_id": event.id,
        "backend_event_at": event.created_at.isoformat(),
        "entity_type": INCIDENT,
        "entity_id": incident_id,
        "payload": payload,
    })


def apply_responder_action(
    db: Session,
    incident_id: str,
    request: ResponderActionRequest,
    user: User,
) -> ResponseLifecycleProjection:
    current = get_lifecycle(db, incident_id)
    if current is None:
        raise LookupError(f"incident {incident_id} not found")
    allowed = {
        "DISPATCHED": "EN_ROUTE",
        "RESPONDING": "EN_ROUTE",
        "EN_ROUTE": "ARRIVED",
        "ARRIVED": "RESOLVED",
    }
    expected = allowed.get(current.status)
    if expected != request.action:
        raise ValueError(f"invalid lifecycle transition {current.status} -> {request.action}")
    if request.action == "RESOLVED":
        if request.preliminary_outcome is None or request.probable_cause is None or request.inspection_required is None or not (request.notes or "").strip():
            raise ValueError("RESOLVED requires preliminary_outcome, probable_cause, inspection_required, and notes")
    payload = {
        "incident_id": incident_id,
        "status": request.action,
        "action": request.action,
        "actor_id": user.id,
        "actor_role": user.role.value,
        "action_timestamp": datetime.now(timezone.utc).isoformat(),
        "preliminary_outcome": request.preliminary_outcome,
        "probable_cause": request.probable_cause,
        "inspection_required": request.inspection_required,
        "notes": request.notes,
    }
    event = append_event(db, event_type=LIFECYCLE_EVENT, entity_type=INCIDENT, entity_id=incident_id, payload=payload, reason_code=f"responder_{request.action.lower()}", human_readable_reason=request.notes)
    _publish(event, payload, LIFECYCLE_EVENT, incident_id)
    return get_lifecycle(db, incident_id)  # type: ignore[return-value]


def apply_operator_lifecycle(
    db: Session,
    incident_id: str,
    request: OperatorLifecycleRequest,
    user: User,
) -> ResponseLifecycleProjection:
    current = get_lifecycle(db, incident_id)
    if current is None:
        raise LookupError(f"incident {incident_id} not found")
    target = {"START_RESPONSE": "RESPONDING", "MANUAL_STOP": "STOPPED", "RESTORE_SAFE_DEFAULT": "SAFE_DEFAULT"}[request.action]
    if request.action == "START_RESPONSE" and current.status != "DISPATCHED":
        raise ValueError(f"cannot start response from {current.status}")
    if request.action != "START_RESPONSE" and current.status in {"VERIFIED", "VERIFIED_FIRE", "REJECTED", "CANCELLED"}:
        raise ValueError(f"incident is already closed as {current.status}")
    if current.status == target:
        raise ValueError(f"duplicate lifecycle action {request.action}")
    payload = {"incident_id": incident_id, "status": target, "action": request.action, "actor_id": user.id, "actor_role": user.role.value, "action_timestamp": datetime.now(timezone.utc).isoformat(), "reason": request.reason}
    event = append_event(db, event_type=OPERATOR_EVENT, entity_type=INCIDENT, entity_id=incident_id, payload=payload, reason_code=f"operator_{request.action.lower()}", human_readable_reason=request.reason)
    _publish(event, payload, OPERATOR_EVENT, incident_id)
    return get_lifecycle(db, incident_id)  # type: ignore[return-value]


def apply_operator_feedback(
    db: Session,
    incident_id: str,
    request: OperatorFeedbackRequest,
    user: User,
) -> ResponseLifecycleProjection:
    current = get_lifecycle(db, incident_id)
    if current is None:
        raise LookupError(f"incident {incident_id} not found")
    if current.status != "RESOLVED":
        raise ValueError("operator feedback requires a RESOLVED responder report")
    payload = {"incident_id": incident_id, "outcome": request.outcome, "status": request.outcome, "operator_id": user.id, "operator_role": user.role.value, "action_timestamp": datetime.now(timezone.utc).isoformat(), "reason": request.reason, "area_id": None}
    event = append_event(db, event_type=FEEDBACK_EVENT, entity_type=INCIDENT, entity_id=incident_id, payload=payload, reason_code=request.outcome, human_readable_reason=request.reason)
    _publish(event, payload, FEEDBACK_EVENT, incident_id)
    return get_lifecycle(db, incident_id)  # type: ignore[return-value]
