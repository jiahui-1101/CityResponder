"""Immutable persistence for versioned route history."""

from sqlalchemy.orm import Session

from app.events.models import Event
from app.events.repository import append_event, get_events_for_entity
from app.routing.versioning import VersionedRoute


def persist_versioned_route(db: Session, route: VersionedRoute) -> Event:
    """Append one route version and reject duplicate route/version identity."""

    existing = get_events_for_entity(
        db,
        entity_type="route",
        entity_id=route.route_id,
        event_type="route_version",
    )
    if any(event.payload.get("version") == route.version for event in existing):
        raise ValueError(
            f"route {route.route_id} version {route.version} is already persisted"
        )

    payload = route.model_dump(mode="json")
    human_reason = "; ".join(
        [
            *route.reasons,
            *(f"warning: {warning}" for warning in route.warnings),
        ]
    ) or None
    return append_event(
        db,
        event_type="route_version",
        entity_type="route",
        entity_id=route.route_id,
        payload=payload,
        reason_code="route_version",
        human_readable_reason=human_reason,
    )
