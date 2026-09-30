"""ADMIN-only calibration governance APIs; no training endpoint is exposed."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.models import User, UserRole
from app.calibration.persistence import activate_version, approve_candidate, rollback_version
from app.calibration.projection import get_active_version, get_candidate, get_candidates, get_validation, get_versions
from app.calibration.schemas import CalibrationCandidate, CalibrationValidationResult, CalibrationVersion
from app.core.database import get_db

router = APIRouter(prefix="/api/admin/calibration", tags=["calibration"])
admin_dependency = Depends(require_role(UserRole.ADMIN))


class CalibrationGovernanceSnapshot(BaseModel):
    active_version: CalibrationVersion | None
    versions: list[CalibrationVersion]
    reasons: list[str]


class CalibrationCandidateView(BaseModel):
    candidate: CalibrationCandidate
    validation: CalibrationValidationResult | None


@router.get("", response_model=CalibrationGovernanceSnapshot)
def governance(db: Session = Depends(get_db), _admin: User = admin_dependency) -> CalibrationGovernanceSnapshot:
    return CalibrationGovernanceSnapshot(active_version=get_active_version(db), versions=get_versions(db), reasons=["Adaptive weights are not connected to Part 3 fusion"])


@router.get("/versions", response_model=list[CalibrationVersion])
def versions(db: Session = Depends(get_db), _admin: User = admin_dependency) -> list[CalibrationVersion]:
    return get_versions(db)


@router.get("/candidates", response_model=list[CalibrationCandidateView])
def candidates(db: Session = Depends(get_db), _admin: User = admin_dependency) -> list[CalibrationCandidateView]:
    return [CalibrationCandidateView(candidate=item, validation=validation) for item, validation in get_candidates(db)]


@router.get("/candidates/{candidate_id}", response_model=CalibrationCandidate)
def candidate(candidate_id: str, db: Session = Depends(get_db), _admin: User = admin_dependency) -> CalibrationCandidate:
    result = get_candidate(db, candidate_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calibration candidate not found")
    return result


@router.post("/candidates/{candidate_id}/approve", response_model=CalibrationVersion, status_code=status.HTTP_201_CREATED)
def approve(candidate_id: str, db: Session = Depends(get_db), admin: User = admin_dependency) -> CalibrationVersion:
    candidate_result = get_candidate(db, candidate_id)
    validation = get_validation(db, candidate_id)
    if candidate_result is None or validation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate or validation result not found")
    try:
        return approve_candidate(db, candidate_result, validation, admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/versions/{version_id}/activate", response_model=CalibrationVersion, status_code=status.HTTP_201_CREATED)
def activate(version_id: str, db: Session = Depends(get_db), admin: User = admin_dependency) -> CalibrationVersion:
    version = next((item for item in get_versions(db) if item.version_id == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calibration version not found")
    try:
        return activate_version(db, version, admin.id, supersedes_version=get_active_version(db).version_number if get_active_version(db) else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/versions/{version_id}/rollback", response_model=CalibrationVersion, status_code=status.HTTP_201_CREATED)
def rollback(version_id: str, db: Session = Depends(get_db), admin: User = admin_dependency) -> CalibrationVersion:
    target = next((item for item in get_versions(db) if item.version_id == version_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calibration version not found")
    try:
        return rollback_version(db, target, admin.id, supersedes_version=get_active_version(db).version_number if get_active_version(db) else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
