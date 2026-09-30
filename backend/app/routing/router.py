"""Authenticated read-only route projections."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.events.schemas import EventRead
from app.routing.projection import RouteIndexItem, RouteProjection, get_route_history, get_route_index, get_route_projection


router = APIRouter(prefix="/api/routes", tags=["routes"])
route_read_dependency = Depends(
    require_any_role(
        UserRole.OPERATOR,
        UserRole.FIREFIGHTER,
        UserRole.RISK_PLANNER,
        UserRole.ADMIN,
    )
)


@router.get("", response_model=list[RouteIndexItem])
def list_routes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = route_read_dependency,
) -> list[RouteIndexItem]:
    """Return newest route projections derived from immutable route events."""

    return get_route_index(db, skip=skip, limit=limit)


@router.get("/{route_id}", response_model=RouteProjection)
def current_route(
    route_id: str,
    db: Session = Depends(get_db),
    _current_user: User = route_read_dependency,
) -> RouteProjection:
    projection = get_route_projection(db, route_id)
    if projection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return projection


@router.get("/{route_id}/history", response_model=list[EventRead])
def route_history(
    route_id: str,
    db: Session = Depends(get_db),
    _current_user: User = route_read_dependency,
) -> list[EventRead]:
    history = get_route_history(db, route_id)
    if history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return history
