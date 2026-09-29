"""Small repository for appending and reading event history."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import Event


def append_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    reason_code: str | None = None,
    human_readable_reason: str | None = None,
) -> Event:
    """Append and persist one event without updating existing history."""

    event = Event(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        reason_code=reason_code,
        human_readable_reason=human_readable_reason,
        payload=payload if payload is not None else {},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_recent_events(
    db: Session,
    *,
    limit: int | None = None,
    event_type: str | None = None,
) -> list[Event]:
    """Return the newest events first with optional type and count filters."""

    statement = select(Event).order_by(Event.created_at.desc(), Event.id.desc())
    if event_type is not None:
        statement = statement.where(Event.event_type == event_type)
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement).all())


def get_events(
    db: Session,
    *,
    limit: int | None = None,
    event_type: str | None = None,
) -> list[Event]:
    """Return recent events through the general read helper."""

    return get_recent_events(db, limit=limit, event_type=event_type)


def get_events_for_entity(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    limit: int | None = None,
    event_type: str | None = None,
) -> list[Event]:
    """Return newest events associated with one entity."""

    statement = (
        select(Event)
        .where(Event.entity_type == entity_type, Event.entity_id == entity_id)
        .order_by(Event.created_at.desc(), Event.id.desc())
    )
    if event_type is not None:
        statement = statement.where(Event.event_type == event_type)
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement).all())
