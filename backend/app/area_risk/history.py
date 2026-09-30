"""Strict operator-verified history selection for Area Risk only."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.area_risk.schemas import VerifiedHistoryWindow, VerifiedIncidentReference
from app.events.models import Event


def get_verified_history_window(
    db: Session,
    *,
    evaluation_time: datetime | None = None,
    area_id: str | None = None,
) -> VerifiedHistoryWindow:
    """Select only explicit operator_decision records in the preceding 180 days."""

    evaluated_at = evaluation_time or datetime.now(timezone.utc)
    window_end = evaluated_at
    window_start = evaluated_at - timedelta(days=180)
    events = list(db.scalars(select(Event).where(Event.event_type == "operator_decision")).all())
    eligible: list[VerifiedIncidentReference] = []
    excluded = 0
    excluded_reasons: list[str] = []
    for event in events:
        payload = event.payload
        action_time_raw = payload.get("action_timestamp")
        try:
            action_time = datetime.fromisoformat(str(action_time_raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            excluded += 1
            excluded_reasons.append(f"event {event.id}: invalid action timestamp")
            continue
        if action_time.tzinfo is None:
            action_time = action_time.replace(tzinfo=timezone.utc)
        if not window_start <= action_time <= window_end:
            excluded += 1
            continue
        explicit_area = payload.get("area_id")
        if area_id is not None and explicit_area != area_id:
            excluded += 1
            continue
        if area_id is None and explicit_area is None:
            excluded += 1
            excluded_reasons.append(f"event {event.id}: no explicit area_id")
            continue
        action = payload.get("action")
        if action not in {"CONFIRM", "REJECT", "CANCEL"}:
            excluded += 1
            excluded_reasons.append(f"event {event.id}: unsupported operator action")
            continue
        eligible.append(VerifiedIncidentReference(
            incident_decision_id=str(payload.get("incident_decision_id", event.entity_id)),
            operator_action=str(action),
            operator_id=payload.get("operator_id"),
            action_timestamp=action_time,
            event_id=event.id,
            area_id=str(explicit_area),
        ))
    eligible.sort(key=lambda item: (item.action_timestamp, item.event_id))
    return VerifiedHistoryWindow(
        evaluation_time=evaluated_at,
        window_start=window_start,
        window_end=window_end,
        eligible_incidents=eligible,
        excluded_record_count=excluded,
        excluded_reasons=excluded_reasons,
        audit_references=[{"event_id": item.event_id, "incident_decision_id": item.incident_decision_id} for item in eligible],
    )
