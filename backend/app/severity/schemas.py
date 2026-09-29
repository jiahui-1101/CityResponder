"""Severity-assessment input contracts without severity assignment."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.fusion.schemas import ConfirmationSequenceResult, FusionSourceReference
from app.vision.schemas import VisionDetectionMessage


class SeverityComponentValues(BaseModel):
    """Explicitly supplied future values for severity A/S/T/Z only."""

    a: float | None = Field(default=None, ge=0.0, le=1.0)
    s: float | None = Field(default=None, ge=0.0, le=1.0)
    t: float | None = Field(default=None, ge=0.0, le=1.0)
    z: float | None = Field(default=None, ge=0.0, le=1.0)
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SeverityInput(BaseModel):
    """Auditable input contract for future severity assessment."""

    status: Literal["not_confirmed", "not_evaluated"]
    confirmation_reference: ConfirmationSequenceResult | None
    incident_confirmed: bool | None
    a: float | None = Field(default=None, ge=0.0, le=1.0)
    s: float | None = Field(default=None, ge=0.0, le=1.0)
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    t: float | None = Field(default=None, ge=0.0, le=1.0)
    z: float | None = Field(default=None, ge=0.0, le=1.0)
    person_in_hazard: bool | None
    person_evidence: VisionDetectionMessage | None
    person_source_timestamp: datetime | None
    critical_override_signal: bool | None
    source_timestamps: dict[str, datetime | None]
    unavailable_inputs: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
