"""Authenticated responder and operator lifecycle APIs."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.lifecycle.schemas import OperatorFeedbackRequest, OperatorLifecycleRequest, ResponderActionRequest, ResponseLifecycleProjection
from app.lifecycle.service import apply_operator_feedback, apply_operator_lifecycle, apply_responder_action, get_lifecycle

router = APIRouter(prefix="/api/incidents", tags=["incident-lifecycle"])
read_roles = Depends(require_any_role(UserRole.OPERATOR, UserRole.FIREFIGHTER, UserRole.RISK_PLANNER))
firefighter_roles = Depends(require_any_role(UserRole.FIREFIGHTER))
operator_roles = Depends(require_any_role(UserRole.OPERATOR))


@router.get("/{incident_id}/lifecycle", response_model=ResponseLifecycleProjection)
def lifecycle(incident_id: str, db=Depends(get_db), _user: User = read_roles):
    result = get_lifecycle(db, incident_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return result


@router.post("/{incident_id}/responder-action", response_model=ResponseLifecycleProjection, status_code=status.HTTP_201_CREATED)
def responder_action(incident_id: str, request: ResponderActionRequest, db=Depends(get_db), user: User = firefighter_roles):
    try:
        return apply_responder_action(db, incident_id, request, user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{incident_id}/operator-lifecycle", response_model=ResponseLifecycleProjection, status_code=status.HTTP_201_CREATED)
def operator_lifecycle(incident_id: str, request: OperatorLifecycleRequest, db=Depends(get_db), user: User = operator_roles):
    try:
        return apply_operator_lifecycle(db, incident_id, request, user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{incident_id}/operator-feedback", response_model=ResponseLifecycleProjection, status_code=status.HTTP_201_CREATED)
def operator_feedback(incident_id: str, request: OperatorFeedbackRequest, db=Depends(get_db), user: User = operator_roles):
    try:
        return apply_operator_feedback(db, incident_id, request, user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
