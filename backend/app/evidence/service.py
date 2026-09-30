"""Explicit selected-frame retention and immutable evidence audit."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import Event
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread
from app.evidence.schemas import (
    FRAME_SELECTION_POLICY,
    MAX_ANNOTATED_FRAMES_PER_INCIDENT,
    RETENTION_DURATION_POLICY,
    SUPPORTED_CONTENT_TYPES,
    EvidenceRetentionResult,
    IncidentEvidenceFrame,
)
from app.evidence.store import EvidenceFrameStore, LocalEvidenceFrameStore, new_evidence_id


class EvidenceLimitReached(ValueError):
    """No sixth selected frame may be silently replaced or deleted."""


def list_incident_evidence(db: Session, decision_id: str) -> list[IncidentEvidenceFrame]:
    events = list(db.scalars(select(Event).where(Event.event_type == "incident_evidence_retained", Event.entity_type == "incident", Event.entity_id == decision_id).order_by(Event.created_at.asc(), Event.id.asc())).all())
    return [IncidentEvidenceFrame.model_validate(event.payload) for event in events]


def get_incident_evidence(db: Session, decision_id: str, evidence_id: str) -> IncidentEvidenceFrame | None:
    return next((item for item in list_incident_evidence(db, decision_id) if item.evidence_id == evidence_id), None)


def retain_incident_evidence_frame(
    db: Session,
    *,
    decision_id: str,
    selected_frame: bytes,
    frame_index: int,
    content_type: str,
    captured_at: datetime,
    annotation_metadata: dict[str, Any],
    source_camera_id: str | None = None,
    reason_codes: list[str] | None = None,
    store: EvidenceFrameStore | None = None,
) -> EvidenceRetentionResult:
    """Store one caller-selected annotated frame; this service is not auto-triggered."""

    incident_exists = db.scalar(select(Event.id).where(Event.event_type == "incident_decision", Event.entity_type == "incident", Event.entity_id == decision_id))
    if incident_exists is None:
        raise ValueError("incident decision does not exist")
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError("unsupported evidence content type")
    if not annotation_metadata:
        raise ValueError("actual annotation metadata is required")
    existing = list_incident_evidence(db, decision_id)
    if len(existing) >= MAX_ANNOTATED_FRAMES_PER_INCIDENT:
        raise EvidenceLimitReached(f"incident already has the maximum {MAX_ANNOTATED_FRAMES_PER_INCIDENT} retained frames")
    evidence_id = new_evidence_id()
    frame_store = store or LocalEvidenceFrameStore()
    reference = frame_store.store(evidence_id, content_type, selected_frame)
    now = datetime.now(timezone.utc)
    evidence = IncidentEvidenceFrame(
        evidence_id=evidence_id,
        incident_decision_id=decision_id,
        captured_at=captured_at,
        stored_at=now,
        frame_index=frame_index,
        content_type=content_type,
        storage_reference=reference,
        annotation_metadata=annotation_metadata,
        source_camera_id=source_camera_id,
        reason_codes=reason_codes or [],
        audit_references=[{"policy": FRAME_SELECTION_POLICY}, {"retention_duration": RETENTION_DURATION_POLICY}],
    )
    try:
        event = append_event(db, event_type="incident_evidence_retained", entity_type="incident", entity_id=decision_id, payload=evidence.model_dump(mode="json"), reason_code="incident_evidence_retained", human_readable_reason="Explicitly selected annotated incident evidence retained")
        publish_live_update_from_thread({"event_type": "incident_evidence_retained", "entity_type": "incident", "entity_id": decision_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": {"evidence_id": evidence.evidence_id, "incident_decision_id": decision_id, "frame_index": evidence.frame_index, "captured_at": evidence.captured_at.isoformat()}})
    except Exception:
        db.rollback()
        raise
    return EvidenceRetentionResult(status="retained", evidence=evidence)
