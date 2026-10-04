"""Immutable persistence adapters for automatic and manual decisions."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events.models import Event, IncidentTransitionClaim
from app.events.repository import append_event, get_events_for_entity
from app.live.service import publish_live_update_from_thread
from app.severity.decision import IncidentDecision
from app.severity.operator import OperatorDecisionResult


INCIDENT_ENTITY_TYPE = "incident"


class IncidentTransitionConflict(ValueError):
    """Raised when another transaction already won incident confirmation."""


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
    if decision.incident_confirmed is True:
        event = Event(
            event_type="incident_decision",
            entity_type=INCIDENT_ENTITY_TYPE,
            entity_id=decision.decision_id,
            payload=payload,
            reason_code="incident_decision",
            human_readable_reason=_join_reasons(decision.reasons, decision.warnings),
        )
        if not _commit_confirmation_claim(
            db,
            incident_id=decision.decision_id,
            winner_type="AUTOMATIC",
            winner_id=decision.decision_id,
            event=event,
        ):
            ignored = append_event(
                db,
                event_type="incident_decision_ignored",
                entity_type=INCIDENT_ENTITY_TYPE,
                entity_id=decision.decision_id,
                payload={**payload, "ignored_reason": "confirmation already claimed"},
                reason_code="CONFIRM_IGNORED_ALREADY_CONFIRMED",
                human_readable_reason="automatic confirmation ignored; another confirmation committed first",
            )
            raise IncidentTransitionConflict(
                f"incident {decision.decision_id} confirmation already claimed; ignored event {ignored.id}"
            )
    else:
        event = append_event(
            db,
            event_type="incident_decision",
            entity_type=INCIDENT_ENTITY_TYPE,
            entity_id=decision.decision_id,
            payload=payload,
            reason_code="incident_decision",
            human_readable_reason=_join_reasons(decision.reasons, decision.warnings),
        )
    publish_live_update_from_thread({"event_type": "incident_decision", "entity_type": INCIDENT_ENTITY_TYPE, "entity_id": decision.decision_id, "event_id": event.id, "backend_event_at": event.created_at.isoformat(), "payload": payload})
    return event


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
    if operator_decision.action.value != "CONFIRM":
        return append_event(
            db,
            event_type="operator_decision",
            entity_type=INCIDENT_ENTITY_TYPE,
            entity_id=operator_decision.incident_decision_id,
            payload=payload,
            reason_code=f"operator_{operator_decision.action.value.lower()}",
            human_readable_reason=operator_decision.written_reason,
        )

    automatic_event = db.scalar(
        select(Event).where(
            Event.event_type == "incident_decision",
            Event.entity_type == INCIDENT_ENTITY_TYPE,
            Event.entity_id == operator_decision.incident_decision_id,
        )
    )
    automatic_confirmed = bool(
        automatic_event is not None
        and automatic_event.payload.get("incident_confirmed") is True
    )
    event = Event(
        event_type="operator_decision",
        entity_type=INCIDENT_ENTITY_TYPE,
        entity_id=operator_decision.incident_decision_id,
        payload=payload,
        reason_code="operator_confirm",
        human_readable_reason=operator_decision.written_reason,
    )
    claimed = False
    if not automatic_confirmed:
        claimed = _commit_confirmation_claim(
            db,
            incident_id=operator_decision.incident_decision_id,
            winner_type="OPERATOR",
            winner_id=operator_decision.action_id,
            event=event,
        )
    if not claimed:
        ignored = append_event(
            db,
            event_type="operator_decision_ignored",
            entity_type=INCIDENT_ENTITY_TYPE,
            entity_id=operator_decision.incident_decision_id,
            payload={**payload, "ignored_reason": "confirmation already claimed"},
            reason_code="CONFIRM_IGNORED_ALREADY_CONFIRMED",
            human_readable_reason="confirm ignored, already confirmed",
        )
        raise IncidentTransitionConflict(
            f"incident {operator_decision.incident_decision_id} confirmation already claimed; ignored event {ignored.id}"
        )
    return event


def _commit_confirmation_claim(
    db: Session,
    *,
    incident_id: str,
    winner_type: str,
    winner_id: str,
    event: Event,
) -> bool:
    """Atomically insert the winner and its immutable event in one transaction."""

    db.add(
        IncidentTransitionClaim(
            incident_id=incident_id,
            winner_type=winner_type,
            winner_id=winner_id,
        )
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    db.refresh(event)
    return True


def _join_reasons(reasons: list[str], warnings: list[str]) -> str | None:
    values: list[str] = []
    values.extend(reasons)
    values.extend(f"warning: {warning}" for warning in warnings)
    return "; ".join(values) if values else None
