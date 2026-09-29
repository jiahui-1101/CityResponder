"""Rebuildable current-route and route-history projections."""

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.events.repository import get_events_for_entity
from app.events.schemas import EventRead
from app.fusion.schemas import FusionSourceReference
from app.routing.versioning import VersionedRoute


class RouteProjection(BaseModel):
    """Latest route-version read model derived from immutable events."""

    route_id: str
    latest_version: int
    previous_version: int | None
    status: str
    source_node_id: str
    destination_node_id: str
    node_path: list[str] = Field(default_factory=list)
    edge_path: list[str] = Field(default_factory=list)
    total_edge_cost: float | None
    total_distance_cm: float | None
    no_safe_route: bool
    route_changed: bool
    invalidates_prior_commands: bool
    created_at: datetime
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    version_count: int
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def get_route_projection(
    db: Session,
    route_id: str,
) -> RouteProjection | None:
    """Return the highest-version route read model, never an older fallback."""

    events = _route_events(db, route_id)
    if not events:
        return None
    versions, warnings = _parse_versions(events, route_id)
    if not versions:
        raise ValueError("route history contains no valid route versions")
    latest_event, latest = max(
        versions,
        key=lambda item: (item[1].version, item[0].id),
    )
    return RouteProjection(
        route_id=route_id,
        latest_version=latest.version,
        previous_version=latest.previous_version,
        status=latest.route_status,
        source_node_id=latest.source_node_id,
        destination_node_id=latest.destination_node_id,
        node_path=list(latest.node_path),
        edge_path=list(latest.edge_path),
        total_edge_cost=latest.total_edge_cost,
        total_distance_cm=latest.total_distance_cm,
        no_safe_route=latest.no_safe_route,
        route_changed=latest.route_changed,
        invalidates_prior_commands=latest.invalidates_prior_commands,
        created_at=latest.created_at,
        reasons=list(latest.reasons),
        warnings=list(latest.warnings) + warnings,
        version_count=len(versions),
        audit_references=list(latest.audit_references),
    )


def get_route_history(db: Session, route_id: str) -> list[EventRead] | None:
    """Return every immutable route-version event ordered by version."""

    events = _route_events(db, route_id)
    if not events:
        return None
    _parse_versions(events, route_id)
    return [EventRead.model_validate(event) for event in events]


def _route_events(db: Session, route_id: str):
    events = get_events_for_entity(
        db,
        entity_type="route",
        entity_id=route_id,
        event_type="route_version",
    )
    return sorted(
        events,
        key=lambda event: (
            _payload_version(event.payload),
            event.id,
        ),
    )


def _parse_versions(events, route_id: str):
    parsed = []
    warnings: list[str] = []
    seen: set[int] = set()
    for event in events:
        payload_route_id = event.payload.get("route_id")
        if payload_route_id != route_id or event.entity_id != route_id:
            warnings.append(f"event {event.id} has mismatched route identity")
        version = _payload_version(event.payload)
        if version <= 0:
            warnings.append(f"event {event.id} has a non-positive route version")
        if version in seen:
            warnings.append(f"duplicate route version {version}")
        seen.add(version)
        try:
            parsed.append((event, VersionedRoute.model_validate(event.payload)))
        except ValueError:
            warnings.append(f"event {event.id} has an invalid route-version payload")
    positive_versions = sorted(version for version in seen if version > 0)
    if positive_versions and positive_versions != list(range(1, positive_versions[-1] + 1)):
        warnings.append("route version history contains an unexpected gap")
    return parsed, warnings


def _payload_version(payload: dict) -> int:
    value = payload.get("version")
    return value if isinstance(value, int) else -1
