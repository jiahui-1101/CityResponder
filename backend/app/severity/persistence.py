"""Immutable persistence adapters for automatic and manual decisions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import Event
from app.events.repository import append_event, get_events_for_entity
from app.severity.decision import IncidentDecision
from app.severity.operator import OperatorDecisionResult


INCIDENT_ENTITY_TYPE = "incident"


def persist_incident_decision(
    db: Session,
    decision: IncidentDecision,
) -> Event:
    """Persist one automatic decision as an immutable event."""

    existing = db.scalar(
        select(Event.id).where(
            Event.event_type == "incident_decision",
            Event.entity_type == INCIDENT_ENTITY_TYPE,
            Event.entity_id == decision.decision_id,
        )
    )
    if existing is not None:
        raise ValueError(
            f"incident decision {decision.decision_id} is already persisted"
        )

    payload = decision.model_dump(mode="json")
    return append_event(
        db,
        event_type="incident_decision",
        entity_type=INCIDENT_ENTITY_TYPE,
        entity_id=decision.decision_id,
        payload=payload,
        reason_code="incident_decision",
        human_readable_reason=_join_reasons(decision.reasons, decision.warnings),
    )


def persist_operator_decision(
    db: Session,
    operator_decision: OperatorDecisionResult,
) -> Event:
    """Persist one manual action without modifying automatic decision history."""

    related_events = get_events_for_entity(
        db,
        entity_type=INCIDENT_ENTITY_TYPE,
        entity_id=operator_decision.incident_decision_id,
        event_type="operator_decision",
    )
    if any(
        event.payload.get("action_id") == operator_decision.action_id
        for event in related_events
    ):
        raise ValueError(
            f"operator decision {operator_decision.action_id} is already persisted"
        )

    payload = operator_decision.model_dump(mode="json")
    return append_event(
        db,
        event_type="operator_decision",
        entity_type=INCIDENT_ENTITY_TYPE,
        entity_id=operator_decision.incident_decision_id,
        payload=payload,
        reason_code=f"operator_{operator_decision.action.value.lower()}",
        human_readable_reason=operator_decision.written_reason,
    )


def _join_reasons(reasons: list[str], warnings: list[str]) -> str | None:
    values: list[str] = []
    values.extend(reasons)
    values.extend(f"warning: {warning}" for warning in warnings)
    return "; ".join(values) if values else None
