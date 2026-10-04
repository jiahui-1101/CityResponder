"""Authenticated REST API for Operator manual decisions."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.events.repository import get_events_for_entity
from app.events.schemas import EventRead
from app.live.service import publish_live_update_from_thread
from app.severity.decision import IncidentDecision
from app.severity.operator import (
    OperatorAction,
    OperatorDecisionRequest,
    OperatorDecisionResult,
    create_operator_decision,
)
from app.severity.persistence import persist_operator_decision
from app.severity.projection import (
    IncidentHistoryProjection,
    IncidentIndexItem,
    get_incident_event_history,
    get_incident_index,
    get_incident_history_projection,
)


router = APIRouter(prefix="/api/incidents", tags=["incidents"])
operator_dependency = Depends(require_any_role(UserRole.OPERATOR))
incident_read_dependency = Depends(
    require_any_role(
        UserRole.OPERATOR,
        UserRole.FIREFIGHTER,
        UserRole.RISK_PLANNER,
        UserRole.ADMIN,
    )
)


@router.get("", response_model=list[IncidentIndexItem])
def list_incidents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = incident_read_dependency,
) -> list[IncidentIndexItem]:
    """Return newest immutable incident projections."""

    return get_incident_index(db, skip=skip, limit=limit)


class OperatorDecisionApiRequest(BaseModel):
    """Request body for a source-backed manual action."""

    action: OperatorAction
    reason: str = Field(min_length=1)
    severity_floor: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason is required")
        return value


@router.get("/{decision_id}", response_model=IncidentHistoryProjection)
def get_incident_projection(
    decision_id: str,
    db: Session = Depends(get_db),
    _current_user: User = incident_read_dependency,
) -> IncidentHistoryProjection:
    """Return the rebuildable current incident projection."""

    projection = get_incident_history_projection(db, decision_id)
    if projection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return projection


@router.get("/{decision_id}/history", response_model=list[EventRead])
def get_incident_history(
    decision_id: str,
    db: Session = Depends(get_db),
    _current_user: User = incident_read_dependency,
) -> list[EventRead]:
    """Return chronological immutable incident and operator events."""

    history = get_incident_event_history(db, decision_id)
    if history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return history


@router.post(
    "/{decision_id}/operator-decision",
    response_model=OperatorDecisionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_operator_decision(
    decision_id: str,
    request: OperatorDecisionApiRequest,
    db: Session = Depends(get_db),
    current_user: User = operator_dependency,
) -> OperatorDecisionResult:
    """Append one authorized manual decision for an existing incident decision."""

    events = get_events_for_entity(
        db,
        entity_type="incident",
        entity_id=decision_id,
        event_type="incident_decision",
        limit=1,
    )
    if not events:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident decision not found")

    try:
        automatic_decision = IncidentDecision.model_validate(events[0].payload)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored incident decision is invalid",
        ) from None

    operator_request = OperatorDecisionRequest(
        operator_id=current_user.id,
        operator_role=current_user.role,
        action=request.action,
        written_reason=request.reason,
        severity_floor=request.severity_floor,
    )
    try:
        result = create_operator_decision(automatic_decision, operator_request)
        persisted_event = persist_operator_decision(db, result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    publish_live_update_from_thread(
        {
            "event_type": "operator_decision",
            "event_id": persisted_event.id,
            "backend_event_at": persisted_event.created_at.isoformat(),
            "entity_type": "incident",
            "entity_id": decision_id,
            "payload": result.model_dump(mode="json"),
        }
    )
    return result
