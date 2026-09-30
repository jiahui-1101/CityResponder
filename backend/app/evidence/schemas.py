"""Metadata-only contracts for selected annotated incident frames."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

MAX_ANNOTATED_FRAMES_PER_INCIDENT = 5
RETENTION_DURATION_POLICY = "TBD_SOURCE"
FRAME_SELECTION_POLICY = "TBD_SOURCE / explicit caller decision"
SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class IncidentEvidenceFrame(BaseModel):
    evidence_id: str
    incident_decision_id: str
    captured_at: datetime
    stored_at: datetime
    frame_index: int = Field(ge=0)
    content_type: str
    storage_reference: str
    annotation_metadata: dict[str, Any] = Field(default_factory=dict)
    source_camera_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    audit_references: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceRetentionResult(BaseModel):
    status: str
    evidence: IncidentEvidenceFrame | None = None
    reason: str | None = None
