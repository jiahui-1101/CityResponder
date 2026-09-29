"""Route identity and version metadata without physical command effects."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.route import RouteCalculationResult


class VersionedRoute(BaseModel):
    """Auditable route result with explicit reroute version metadata."""

    route_id: str
    version: int = Field(gt=0)
    previous_version: int | None = Field(default=None, gt=0)
    route_status: str
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
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def version_route(
    current_result: RouteCalculationResult,
    previous_route: VersionedRoute | None = None,
    route_id: str | None = None,
) -> VersionedRoute:
    """Assign route identity/version without persisting or dispatching."""

    if previous_route is not None and previous_route.version <= 0:
        raise ValueError("previous route version must be positive")
    if previous_route is not None and route_id is not None:
        if route_id != previous_route.route_id:
            raise ValueError("route_id must match the previous route identity")
    if route_id is not None and not route_id.strip():
        raise ValueError("route_id must not be blank")

    identity = route_id or (
        previous_route.route_id if previous_route is not None else str(uuid4())
    )
    _validate_uuid_if_generated(identity, route_id, previous_route)

    changed = previous_route is None or _route_outcome_changed(
        current_result,
        previous_route,
    )
    if previous_route is None:
        version = 1
        previous_version = None
        invalidates = False
    elif changed:
        version = previous_route.version + 1
        previous_version = previous_route.version
        invalidates = True
    else:
        version = previous_route.version
        previous_version = previous_route.previous_version
        invalidates = False

    return VersionedRoute(
        route_id=identity,
        version=version,
        previous_version=previous_version,
        route_status=current_result.status,
        source_node_id=current_result.source_node_id,
        destination_node_id=current_result.destination_node_id,
        node_path=list(current_result.node_path),
        edge_path=list(current_result.edge_path),
        total_edge_cost=current_result.total_edge_cost,
        total_distance_cm=current_result.total_distance_cm,
        no_safe_route=current_result.no_safe_route,
        route_changed=changed,
        invalidates_prior_commands=invalidates,
        created_at=datetime.now(timezone.utc),
        reasons=list(current_result.reasons),
        warnings=list(current_result.warnings),
        audit_references=list(current_result.audit_references),
    )


def _route_outcome_changed(
    current: RouteCalculationResult,
    previous: VersionedRoute,
) -> bool:
    return (
        current.status != previous.route_status
        or current.no_safe_route != previous.no_safe_route
        or current.node_path != previous.node_path
        or current.edge_path != previous.edge_path
    )


def _validate_uuid_if_generated(
    identity: str,
    supplied_route_id: str | None,
    previous_route: VersionedRoute | None,
) -> None:
    if supplied_route_id is not None or previous_route is not None:
        return
    try:
        UUID(identity)
    except ValueError as exc:
        raise ValueError("generated route identity must be a UUID") from exc
