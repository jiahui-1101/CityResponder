"""Authenticated read-only incident evidence APIs."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.evidence.schemas import IncidentEvidenceFrame
from app.evidence.service import get_incident_evidence, list_incident_evidence
from app.evidence.store import LocalEvidenceFrameStore

router = APIRouter(prefix="/api/incidents", tags=["incident-evidence"])
evidence_read_dependency = Depends(require_any_role(UserRole.OPERATOR, UserRole.FIREFIGHTER, UserRole.RISK_PLANNER, UserRole.ADMIN))


@router.get("/{decision_id}/evidence", response_model=list[IncidentEvidenceFrame])
def incident_evidence(decision_id: str, db: Session = Depends(get_db), _user: User = evidence_read_dependency) -> list[IncidentEvidenceFrame]:
    return list_incident_evidence(db, decision_id)


@router.get("/{decision_id}/evidence/{evidence_id}")
def incident_evidence_image(decision_id: str, evidence_id: str, db: Session = Depends(get_db), _user: User = evidence_read_dependency) -> Response:
    evidence = get_incident_evidence(db, decision_id, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident evidence not found")
    stored = LocalEvidenceFrameStore().retrieve(evidence_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retained evidence image not found")
    path, content_type = stored
    return FileResponse(path, media_type=content_type, filename=f"{evidence_id}{path.suffix}")
