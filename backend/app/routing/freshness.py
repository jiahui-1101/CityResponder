"""Route-version freshness checks for traffic command execution."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import Event
from app.events.repository import append_event
from app.fusion.schemas import FusionSourceReference
from app.physical_actions.schemas import ActionCategory, PhysicalActionCommandSpec
from app.routing.projection import get_route_projection


class TrafficCommandValidityResult(BaseModel):
    """Read-only route-version validation for one traffic command."""

    status: str
    valid_for_execution: bool
    route_id: str | None
    command_route_version: int | None
    latest_route_version: int | None
    stale: bool
    invalidated: bool
    reason: str
    checked_at: datetime
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def validate_traffic_command_route_version(
    db: Session,
    command_spec: PhysicalActionCommandSpec,
    *,
    command_id: str | None = None,
) -> TrafficCommandValidityResult:
    """Validate explicit traffic route metadata against immutable route history."""

    checked_at = datetime.now(timezone.utc)
    if command_spec.action_category is not ActionCategory.TRAFFIC:
        return TrafficCommandValidityResult(
            status="not_applicable",
            valid_for_execution=True,
            route_id=command_spec.route_id,
            command_route_version=command_spec.route_version,
            latest_route_version=None,
            stale=False,
            invalidated=False,
            reason="route-version validation applies only to TRAFFIC commands",
            checked_at=checked_at,
        )
    if command_spec.route_id is None or command_spec.route_version is None:
        return TrafficCommandValidityResult(
            status="invalid_configuration",
            valid_for_execution=False,
            route_id=command_spec.route_id,
            command_route_version=command_spec.route_version,
            latest_route_version=None,
            stale=False,
            invalidated=False,
            reason="route-aware traffic command requires route_id and route_version",
            checked_at=checked_at,
        )

    try:
        projection = get_route_projection(db, command_spec.route_id)
    except ValueError as exc:
        projection = None
        reason = f"route projection is invalid: {exc}"
    else:
        reason = ""
    if projection is None:
        return TrafficCommandValidityResult(
            status="unresolved",
            valid_for_execution=False,
            route_id=command_spec.route_id,
            command_route_version=command_spec.route_version,
            latest_route_version=None,
            stale=False,
            invalidated=False,
            reason=reason or "route_id was not found in immutable route history",
            checked_at=checked_at,
        )

    latest = projection.latest_version
    if command_spec.route_version == latest:
        return TrafficCommandValidityResult(
            status="valid",
            valid_for_execution=True,
            route_id=command_spec.route_id,
            command_route_version=command_spec.route_version,
            latest_route_version=latest,
            stale=False,
            invalidated=False,
            reason="traffic command route version matches latest route version",
            checked_at=checked_at,
            audit_references=list(projection.audit_references),
        )
    if command_spec.route_version < latest:
        reason = "traffic command route version is stale and invalidated"
        _append_invalidation_event(
            db,
            command_spec,
            latest_version=latest,
            reason=reason,
            command_id=command_id,
            checked_at=checked_at,
        )
        return TrafficCommandValidityResult(
            status="stale_route_version",
            valid_for_execution=False,
            route_id=command_spec.route_id,
            command_route_version=command_spec.route_version,
            latest_route_version=latest,
            stale=True,
            invalidated=True,
            reason=reason,
            checked_at=checked_at,
            audit_references=list(projection.audit_references),
        )
    return TrafficCommandValidityResult(
        status="invalid_configuration",
        valid_for_execution=False,
        route_id=command_spec.route_id,
        command_route_version=command_spec.route_version,
        latest_route_version=latest,
        stale=False,
        invalidated=False,
        reason="traffic command route version is newer than the latest route version",
        checked_at=checked_at,
        audit_references=list(projection.audit_references),
    )


def _append_invalidation_event(
    db: Session,
    command_spec: PhysicalActionCommandSpec,
    *,
    latest_version: int,
    reason: str,
    command_id: str | None,
    checked_at: datetime,
) -> None:
    existing = db.scalars(
        select(Event).where(
            Event.event_type == "traffic_command_invalidated",
            Event.entity_type == "route",
            Event.entity_id == command_spec.route_id,
        )
    ).all()
    if any(
        event.payload.get("spec_id") == command_spec.spec_id
        and event.payload.get("stale_version") == command_spec.route_version
        and event.payload.get("command_id") == command_id
        for event in existing
    ):
        return
    append_event(
        db,
        event_type="traffic_command_invalidated",
        entity_type="route",
        entity_id=command_spec.route_id,
        payload={
            "route_id": command_spec.route_id,
            "stale_version": command_spec.route_version,
            "latest_version": latest_version,
            "spec_id": command_spec.spec_id,
            "command_id": command_id,
            "reason": reason,
            "timestamp": checked_at.isoformat(),
        },
        reason_code="traffic_command_invalidated",
        human_readable_reason=reason,
    )
