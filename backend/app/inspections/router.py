"""Inspection queue, mutation, and CSV export APIs."""

import csv
import io
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.events.models import Event
from app.events.repository import append_event
from app.live.service import publish_live_update_from_thread

router = APIRouter(prefix="/api/inspections", tags=["inspections"])
read_roles = Depends(require_any_role(UserRole.OPERATOR, UserRole.RISK_PLANNER))
write_roles = Depends(require_any_role(UserRole.OPERATOR, UserRole.RISK_PLANNER))


class InspectionRequest(BaseModel):
    area_id: str = Field(min_length=1)
    incident_id: str | None = None
    reason: str = Field(min_length=1)
    status: str = "OPEN"
    notes: str | None = None


class InspectionUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


def _rows(db: Session) -> list[dict]:
    events = list(db.scalars(select(Event).where(Event.entity_type == "inspection").order_by(Event.created_at.asc(), Event.id.asc())).all())
    current: dict[str, dict] = {}
    for event in events:
        payload = dict(event.payload)
        item = current.setdefault(event.entity_id, {"inspection_id": event.entity_id})
        item.update(payload)
        item["updated_at"] = event.created_at
    return sorted(current.values(), key=lambda item: item.get("updated_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)


@router.get("")
def list_inspections(db: Session = Depends(get_db), _user: User = read_roles):
    return _rows(db)


@router.get("/export.csv")
def export_inspections(db: Session = Depends(get_db), _user: User = read_roles):
    rows = _rows(db)
    output = io.StringIO()
    fields = ["inspection_id", "area_id", "incident_id", "reason", "status", "notes", "created_at", "updated_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=cityresponder-inspections.csv"})


@router.post("", status_code=status.HTTP_201_CREATED)
def create_inspection(request: InspectionRequest, db: Session = Depends(get_db), user: User = write_roles):
    inspection_id = str(uuid4())
    payload = {"inspection_id": inspection_id, **request.model_dump(), "created_by": user.id}
    event = append_event(db, event_type="inspection_created", entity_type="inspection", entity_id=inspection_id, payload=payload, reason_code="inspection_created", human_readable_reason=request.reason)
    publish_live_update_from_thread({"event_type": "inspection_created", "event_id": event.id, "entity_type": "inspection", "entity_id": inspection_id, "backend_event_at": event.created_at.isoformat(), "payload": payload})
    return payload


@router.patch("/{inspection_id}")
def update_inspection(inspection_id: str, request: InspectionUpdate, db: Session = Depends(get_db), user: User = write_roles):
    rows = {row["inspection_id"]: row for row in _rows(db)}
    if inspection_id not in rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    payload = {"inspection_id": inspection_id, **request.model_dump(exclude_none=True), "updated_by": user.id}
    event = append_event(db, event_type="inspection_updated", entity_type="inspection", entity_id=inspection_id, payload=payload, reason_code="inspection_updated", human_readable_reason=request.notes)
    publish_live_update_from_thread({"event_type": "inspection_updated", "event_id": event.id, "entity_type": "inspection", "entity_id": inspection_id, "backend_event_at": event.created_at.isoformat(), "payload": payload})
    return {**rows[inspection_id], **payload}
