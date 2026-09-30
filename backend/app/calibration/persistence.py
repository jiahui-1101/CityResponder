"""Append-only calibration governance persistence."""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calibration.schemas import CalibrationCandidate, CalibrationValidationResult, CalibrationVersion
from app.events.models import Event
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread


def _has_event(db: Session, event_type: str, entity_id: str) -> bool:
    return db.scalar(select(Event.id).where(Event.event_type == event_type, Event.entity_id == entity_id)) is not None


def _next_version_number(db: Session) -> int:
    events = db.scalars(select(Event).where(Event.entity_type == "calibration")).all()
    numbers = [int(event.payload["version_number"]) for event in events if str(event.payload.get("version_number", "")).isdigit()]
    return max(numbers, default=0) + 1


def persist_candidate(db: Session, candidate: CalibrationCandidate) -> Event:
    if _has_event(db, "calibration_candidate", candidate.candidate_id):
        raise ValueError(f"calibration candidate {candidate.candidate_id} is already persisted")
    payload = candidate.model_dump(mode="json")
    event = append_event(db, event_type="calibration_candidate", entity_type="calibration_candidate", entity_id=candidate.candidate_id, payload=payload, reason_code="calibration_candidate")
    publish_live_update_from_thread({"event_type": "calibration_candidate", "entity_type": "calibration_candidate", "entity_id": candidate.candidate_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": {"candidate_id": candidate.candidate_id, "status": candidate.status}})
    return event


def persist_validation(db: Session, result: CalibrationValidationResult) -> Event:
    if _has_event(db, "calibration_validation", result.candidate_id):
        raise ValueError(f"calibration validation for {result.candidate_id} is already persisted")
    payload = result.model_dump(mode="json")
    event = append_event(db, event_type="calibration_validation", entity_type="calibration_candidate", entity_id=result.candidate_id, payload=payload, reason_code="calibration_validation")
    publish_live_update_from_thread({"event_type": "calibration_validation", "entity_type": "calibration_candidate", "entity_id": result.candidate_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": {"candidate_id": result.candidate_id, "status": result.status, "passed": result.passed}})
    return event


def persist_calibration_version(db: Session, version: CalibrationVersion, event_type: str) -> Event:
    if event_type not in {"calibration_version_approved", "calibration_version_activated", "calibration_version_rollback"}:
        raise ValueError("unsupported calibration version event type")
    if _has_event(db, event_type, version.version_id):
        raise ValueError(f"calibration version {version.version_id} is already persisted")
    payload = version.model_dump(mode="json")
    event = append_event(db, event_type=event_type, entity_type="calibration", entity_id=version.version_id, payload=payload, reason_code=event_type)
    publish_live_update_from_thread({"event_type": event_type, "entity_type": "calibration", "entity_id": version.version_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": {"version_id": version.version_id, "version_number": version.version_number, "status": version.status}})
    return event


def approve_candidate(db: Session, candidate: CalibrationCandidate, validation: CalibrationValidationResult, admin_id: int) -> CalibrationVersion:
    if candidate.projected_candidate_weights is None or candidate.status not in {"candidate_ready", "approved"}:
        raise ValueError("candidate does not contain valid projected weights")
    if candidate.training_count != 30 or candidate.validation_count != 15:
        raise ValueError("candidate dataset does not satisfy the required 30/15 split")
    if validation.candidate_id != candidate.candidate_id or validation.passed is not True:
        raise ValueError("candidate requires an explicit passed validation result")
    now = datetime.now(timezone.utc)
    version = CalibrationVersion(version_number=_next_version_number(db), weights=candidate.projected_candidate_weights, source_candidate_id=candidate.candidate_id, status="approved", approved_by=admin_id, approved_at=now, created_at=now, reasons=["approved by authenticated ADMIN"])
    persist_calibration_version(db, version, "calibration_version_approved")
    return version


def activate_version(db: Session, approved: CalibrationVersion, admin_id: int, *, supersedes_version: int | None = None) -> CalibrationVersion:
    if approved.status not in {"approved", "active"}:
        raise ValueError("only an approved calibration version may be activated")
    now = datetime.now(timezone.utc)
    version = CalibrationVersion(
        version_number=_next_version_number(db),
        weights=approved.weights,
        source_candidate_id=approved.source_candidate_id,
        status="active",
        approved_by=approved.approved_by or admin_id,
        approved_at=approved.approved_at,
        activated_at=now,
        supersedes_version=supersedes_version,
        reasons=["activation by authenticated ADMIN"],
        created_at=now,
    )
    persist_calibration_version(db, version, "calibration_version_activated")
    return version


def rollback_version(db: Session, target: CalibrationVersion, admin_id: int, *, supersedes_version: int | None = None) -> CalibrationVersion:
    if target.status not in {"approved", "active"}:
        raise ValueError("rollback target must be an approved valid version")
    now = datetime.now(timezone.utc)
    version = CalibrationVersion(version_number=_next_version_number(db), weights=target.weights, source_candidate_id=target.source_candidate_id, status="active", approved_by=admin_id, approved_at=target.approved_at, activated_at=now, supersedes_version=supersedes_version, rollback_from_version=target.version_number, reasons=["rollback by authenticated ADMIN"], created_at=now)
    persist_calibration_version(db, version, "calibration_version_rollback")
    return version
