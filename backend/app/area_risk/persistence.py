"""Append-only persistence for explicitly calculated Area Risk results."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.area_risk.schemas import AreaRiskResult
from app.events.models import Event
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread


def persist_area_risk(db: Session, result: AreaRiskResult) -> Event:
    """Append one calculation snapshot; identical area/time snapshots are rejected."""

    duplicate = db.scalar(
        select(Event).where(
            Event.event_type == "area_risk_calculated",
            Event.entity_type == "area",
            Event.entity_id == result.area_id,
        ).where(Event.payload["calculated_at"].as_string() == result.calculated_at.isoformat())
    )
    if duplicate is not None:
        raise ValueError(f"area risk calculation {result.area_id}/{result.calculated_at.isoformat()} is already persisted")
    event = append_event(
        db,
        event_type="area_risk_calculated",
        entity_type="area",
        entity_id=result.area_id,
        payload=result.model_dump(mode="json"),
        reason_code="area_risk_calculated",
        human_readable_reason="Area Risk Index calculation snapshot",
    )
    publish_live_update_from_thread({"event_type": "area_risk_calculated", "entity_type": "area", "entity_id": result.area_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": {"area_id": result.area_id, "score": result.score, "calculated_at": result.calculated_at.isoformat()}})
    return event
