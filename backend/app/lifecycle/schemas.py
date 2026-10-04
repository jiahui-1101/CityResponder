"""Append-only incident response lifecycle schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.events.schemas import EventRead

ResponderAction = Literal["EN_ROUTE", "ARRIVED", "RESOLVED"]
OperatorLifecycleAction = Literal["START_RESPONSE", "MANUAL_STOP", "RESTORE_SAFE_DEFAULT"]
PreliminaryOutcome = Literal["FIRE", "FALSE_ALARM", "UNKNOWN"]
VerifiedOutcome = Literal["VERIFIED_FIRE", "VERIFIED_FALSE_ALARM"]


class ResponderActionRequest(BaseModel):
    action: ResponderAction
    preliminary_outcome: PreliminaryOutcome | None = None
    probable_cause: str | None = None
    inspection_required: bool | None = None
    notes: str | None = None


class OperatorLifecycleRequest(BaseModel):
    action: OperatorLifecycleAction
    reason: str = Field(min_length=1)


class OperatorFeedbackRequest(BaseModel):
    outcome: VerifiedOutcome
    reason: str = Field(min_length=1)


class ResponseLifecycleProjection(BaseModel):
    incident_id: str
    status: str
    status_changed_at: datetime | None = None
    preliminary_outcome: PreliminaryOutcome | None = None
    probable_cause: str | None = None
    inspection_required: bool | None = None
    notes: str | None = None
    verified_outcome: VerifiedOutcome | None = None
    events: list[EventRead] = Field(default_factory=list)
