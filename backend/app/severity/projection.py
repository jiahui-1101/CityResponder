"""Rebuildable read-only incident history and outcome projections."""

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.events.models import Event
from app.events.repository import get_events_for_entity
from app.events.schemas import EventRead
from app.severity.decision import IncidentDecision
from app.severity.operator import OperatorDecisionResult


class IncidentHistoryProjection(BaseModel):
    """Read model derived exclusively from immutable incident events."""

    incident_id: str
    automatic_decision: IncidentDecision
    operator_actions: list[OperatorDecisionResult] = Field(default_factory=list)
    latest_operator_action: OperatorDecisionResult | None
    projected_outcome: str
    final_severity: str | None
    created_at: datetime
    evaluated_at: datetime
    audit_timeline: list[EventRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def get_incident_history_projection(
    db: Session,
    decision_id: str,
) -> IncidentHistoryProjection | None:
    """Build the current read-only projection for one incident decision ID."""

    events = _incident_events(db, decision_id)
    automatic_event = next(
        (event for event in events if event.event_type == "incident_decision"),
        None,
    )
    if automatic_event is None:
        return None

    warnings: list[str] = []
    try:
        automatic = IncidentDecision.model_validate(automatic_event.payload)
    except ValueError:
        raise ValueError("stored incident decision payload is invalid") from None

    operator_actions: list[OperatorDecisionResult] = []
    for event in events:
        if event.event_type != "operator_decision":
            continue
        try:
            operator_actions.append(OperatorDecisionResult.model_validate(event.payload))
        except ValueError:
            warnings.append(f"operator event {event.id} has an invalid payload")

    latest = _latest_operator_action(events, operator_actions)
    projected_outcome = (
        latest.resulting_operator_outcome
        if latest is not None
        else automatic.decision_status
    )
    if latest is not None:
        warnings.append(
            "projected_outcome is a read-model convenience, not a source-defined lifecycle state"
        )

    return IncidentHistoryProjection(
        incident_id=decision_id,
        automatic_decision=automatic,
        operator_actions=operator_actions,
        latest_operator_action=latest,
        projected_outcome=projected_outcome,
        final_severity=automatic.final_severity,
        created_at=automatic_event.created_at,
        evaluated_at=automatic.evaluated_at,
        audit_timeline=[EventRead.model_validate(event) for event in events],
        warnings=warnings,
    )


def get_incident_event_history(db: Session, decision_id: str) -> list[EventRead] | None:
    """Return chronological immutable events for one incident decision ID."""

    events = _incident_events(db, decision_id)
    if not any(event.event_type == "incident_decision" for event in events):
        return None
    return [EventRead.model_validate(event) for event in events]


def _incident_events(db: Session, decision_id: str) -> list[Event]:
    events = get_events_for_entity(
        db,
        entity_type="incident",
        entity_id=decision_id,
    )
    return sorted(events, key=lambda event: (event.created_at, event.id))


def _latest_operator_action(
    events: list[Event],
    actions: list[OperatorDecisionResult],
) -> OperatorDecisionResult | None:
    by_action_id = {action.action_id: action for action in actions}
    ordered = [
        event
        for event in events
        if event.event_type == "operator_decision"
        and event.payload.get("action_id") in by_action_id
    ]
    if not ordered:
        return None
    latest_event = max(ordered, key=lambda event: (event.created_at, event.id))
    return by_action_id[latest_event.payload["action_id"]]
