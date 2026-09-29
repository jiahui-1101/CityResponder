"""Part 3 severity-assessment contracts."""

from app.severity.calculator import (
    SEVERITY_WEIGHTS,
    SeverityScoreResult,
    calculate_severity_score,
)
from app.severity.classification import (
    SeverityClassificationPolicy,
    SeverityClassificationResult,
    classify_severity,
)
from app.severity.decision import IncidentDecision, build_incident_decision
from app.severity.operator import (
    OperatorAction,
    OperatorDecisionRequest,
    OperatorDecisionResult,
    create_operator_decision,
)
from app.severity.persistence import (
    persist_incident_decision,
    persist_operator_decision,
)

__all__ = [
    "SEVERITY_WEIGHTS",
    "SeverityScoreResult",
    "calculate_severity_score",
    "SeverityClassificationPolicy",
    "SeverityClassificationResult",
    "classify_severity",
    "IncidentDecision",
    "build_incident_decision",
    "OperatorAction",
    "OperatorDecisionRequest",
    "OperatorDecisionResult",
    "create_operator_decision",
    "persist_incident_decision",
    "persist_operator_decision",
]
