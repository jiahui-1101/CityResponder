"""Authenticated Operator manual-decision contracts without persistence."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.auth.models import UserRole
from app.fusion.schemas import FusionSourceReference
from app.severity.decision import IncidentDecision


class OperatorAction(str, Enum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    CANCEL = "CANCEL"


class OperatorDecisionRequest(BaseModel):
    """Validated input for one attributable manual action."""

    operator_id: int
    operator_role: UserRole
    action: OperatorAction
    written_reason: str
    action_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("written_reason")
    @classmethod
    def require_written_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("written_reason is required")
        return value


class OperatorDecisionResult(BaseModel):
    """Auditable manual outcome kept separate from automatic evidence."""

    action_id: str
    incident_decision_id: str
    operator_id: int
    operator_role: UserRole
    action: OperatorAction
    written_reason: str
    previous_automatic_decision_status: str
    resulting_operator_outcome: str
    action_timestamp: datetime
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


def create_operator_decision(
    incident_decision: IncidentDecision,
    request: OperatorDecisionRequest,
) -> OperatorDecisionResult:
    """Create an authorized manual result without changing the automatic decision."""

    if request.operator_role not in {UserRole.OPERATOR, UserRole.ADMIN}:
        raise PermissionError("only OPERATOR or ADMIN may perform manual decisions")

    action_id = str(uuid4())
    audit_reference = FusionSourceReference(
        source_type="operator_decision",
        source_id=action_id,
        timestamp=request.action_timestamp,
    )
    return OperatorDecisionResult(
        action_id=action_id,
        incident_decision_id=incident_decision.decision_id,
        operator_id=request.operator_id,
        operator_role=request.operator_role,
        action=request.action,
        written_reason=request.written_reason,
        previous_automatic_decision_status=incident_decision.decision_status,
        resulting_operator_outcome=request.action.value,
        action_timestamp=request.action_timestamp,
        audit_references=[audit_reference],
    )
