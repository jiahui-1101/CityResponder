"""Authenticated read-only Area Risk APIs."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.area_risk.projection import get_area_risk, get_area_risk_history, get_area_risk_index
from app.area_risk.schemas import AreaRiskResult
from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db

router = APIRouter(prefix="/api/risk", tags=["area-risk"])
risk_dependency = Depends(require_any_role(UserRole.RISK_PLANNER))


@router.get("/areas", response_model=list[AreaRiskResult])
def list_risk_areas(db: Session = Depends(get_db), _user: User = risk_dependency) -> list[AreaRiskResult]:
    return get_area_risk_index(db)


@router.get("/areas/{area_id}", response_model=AreaRiskResult)
def risk_area(area_id: str, db: Session = Depends(get_db), _user: User = risk_dependency) -> AreaRiskResult:
    result = get_area_risk(db, area_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Area risk not found")
    return result


@router.get("/areas/{area_id}/history", response_model=list[AreaRiskResult])
def risk_area_history(area_id: str, db: Session = Depends(get_db), _user: User = risk_dependency) -> list[AreaRiskResult]:
    history = get_area_risk_history(db, area_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Area risk not found")
    return history
