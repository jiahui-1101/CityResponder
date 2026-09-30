"""Read-only Area Risk projections from immutable calculation events."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.area_risk.schemas import AreaRiskResult
from app.events.models import Event


def _events(db: Session, area_id: str | None = None) -> list[Event]:
    statement = select(Event).where(Event.event_type == "area_risk_calculated", Event.entity_type == "area")
    if area_id is not None:
        statement = statement.where(Event.entity_id == area_id)
    return list(db.scalars(statement).all())


def get_area_risk_history(db: Session, area_id: str) -> list[AreaRiskResult]:
    events = sorted(_events(db, area_id), key=lambda event: (event.created_at, event.id))
    return [AreaRiskResult.model_validate(event.payload) for event in events]


def get_area_risk(db: Session, area_id: str) -> AreaRiskResult | None:
    history = get_area_risk_history(db, area_id)
    return history[-1] if history else None


def get_area_risk_index(db: Session) -> list[AreaRiskResult]:
    events = sorted(_events(db), key=lambda event: (event.created_at, event.id), reverse=True)
    latest: dict[str, Event] = {}
    for event in events:
        latest.setdefault(event.entity_id, event)
    return [AreaRiskResult.model_validate(event.payload) for event in sorted(latest.values(), key=lambda item: item.entity_id)]
