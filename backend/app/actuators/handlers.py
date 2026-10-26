"""Correlated AC1 ACK ingestion into immutable events and live updates."""

import logging
from typing import Any

from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter

from app.actuators.ack_waiter import notify_actuator_ack
from app.actuators.schemas import ActuatorAckMessage, ActuatorCommand
from app.core.database import SessionLocal
from app.events.models import Event
from app.events.repository import append_event, get_events_for_entity
from app.live.service import publish_live_update_from_thread


logger = logging.getLogger(__name__)
ack_adapter = TypeAdapter(ActuatorAckMessage)
command_adapter = TypeAdapter(ActuatorCommand)


def handle_ack_message(topic: str, payload: Any) -> None:
    """Validate topic, command, and ACK stage before changing command state."""

    if not isinstance(payload, dict):
        _record_rejection(topic, payload, "JSON_OBJECT_REQUIRED")
        return

    try:
        ack = ack_adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning("Invalid actuator ACK on %s: %s", topic, exc.errors())
        _record_rejection(topic, payload, "MALFORMED_ACK")
        return

    stage = ack.stage or {
        "RECEIVED": "received",
        "ACK": "execution_reported",
        "EXECUTED": "execution_reported",
        "FAILED": "failed",
        "REJECTED": "failed",
    }[ack.status]

    if payload.get("simulated") is True or str(payload.get("source", "")).lower() == "simulation":
        _record_rejection(topic, payload, "SIMULATION_ACK_FORBIDDEN")
        return
    if topic != f"city/acks/{ack.node_id}":
        _record_rejection(topic, payload, "ACK_TOPIC_DEVICE_MISMATCH")
        return

    db = SessionLocal()
    event: Event | None = None
    try:
        history = get_events_for_entity(
            db,
            entity_type="command",
            entity_id=ack.command_id,
        )
        command_event = next(
            (item for item in history if item.event_type == "actuator_command"),
            None,
        )
        if command_event is None:
            reason = "UNKNOWN_COMMAND_ID"
        else:
            try:
                command = command_adapter.validate_python(command_event.payload)
            except ValidationError:
                command = None
                reason = "STORED_COMMAND_MALFORMED"

            if command is not None:
                if command.command_id != ack.command_id:
                    reason = "COMMAND_ID_MISMATCH"
                elif command.node_id != ack.node_id:
                    reason = "WRONG_DEVICE_ID"
                elif not _action_matches(command, ack):
                    reason = "ACK_ACTION_MISMATCH"
                else:
                    accepted_acks = [item for item in history if item.event_type == "actuator_ack"]
                    terminal = next(
                        (
                            item
                            for item in accepted_acks
                            if item.payload.get("ack_stage") in {"execution_reported", "failed"}
                        ),
                        None,
                    )
                    same_stage = next(
                        (item for item in accepted_acks if item.payload.get("ack_stage") == stage),
                        None,
                    )
                    if same_stage is not None:
                        logger.info("Duplicate actuator ACK ignored for command %s", ack.command_id)
                        return
                    if terminal is not None:
                        reason = "ACK_OUT_OF_ORDER_OR_ALREADY_TERMINAL"
                    else:
                        timed_out = any(
                            item.event_type == "actuator_ack_timeout" for item in history
                        )
                        accepted_payload = {
                            **payload,
                            "ack_stage": stage,
                            "late": timed_out,
                            "mqtt_topic": topic,
                        }
                        event = append_event(
                            db,
                            event_type="actuator_ack",
                            entity_type="command",
                            entity_id=ack.command_id,
                            payload=accepted_payload,
                            reason_code=(
                                "ACK_EXECUTION_REPORTED"
                                if stage == "execution_reported"
                                else "ACK_DEVICE_RECEIVED"
                                if stage == "received"
                                else "ACK_DEVICE_FAILED"
                            ),
                            human_readable_reason=(
                                "AC1 reported that the requested output command was applied"
                                if stage == "execution_reported"
                                else "AC1 validated and received the command"
                                if stage == "received"
                                else "AC1 rejected or failed the requested operation"
                            ),
                        )
                        if stage != "received":
                            notify_actuator_ack(
                                ack.command_id,
                                ack.node_id,
                                accepted_payload,
                                ack.timestamp,
                            )
        if event is None:
            _append_rejection(db, topic, payload, reason)
            return
    except Exception:
        db.rollback()
        logger.exception("Failed to validate or store actuator ACK from %s", topic)
        return
    finally:
        db.close()

    publish_live_update_from_thread(
        {
            "event_type": event.event_type,
            "event_id": event.id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": event.payload,
        }
    )


def _action_matches(command: ActuatorCommand, ack: ActuatorAckMessage) -> bool:
    """If present, ACK action fields must agree with the command envelope."""

    expected_category = command.payload.get("action_category")
    expected_action = command.payload.get("action_type")
    if ack.action_category is not None and ack.action_category != expected_category:
        return False
    if ack.action_type is not None and ack.action_type != expected_action:
        return False
    return True


def _record_rejection(topic: str, payload: Any, reason: str) -> None:
    db = SessionLocal()
    try:
        _append_rejection(db, topic, payload, reason)
    except Exception:
        db.rollback()
        logger.exception("Failed to store rejected actuator ACK from %s", topic)
    finally:
        db.close()


def _append_rejection(db: Any, topic: str, payload: Any, reason: str) -> None:
    """Record only bounded identifiers for invalid/untrusted ACK data."""

    command_id = payload.get("command_id") if isinstance(payload, dict) else None
    if not isinstance(command_id, str) or not command_id:
        command_id = "unmatched"
    event = append_event(
        db,
        event_type="actuator_ack_rejected",
        entity_type="command",
        entity_id=command_id[:255],
        reason_code=reason,
        human_readable_reason="Actuator ACK was rejected before command state changed",
        payload={
            "command_id": command_id[:255],
            "topic": str(topic)[:255],
            "reason": reason,
        },
    )
    logger.warning("Rejected actuator ACK on %s: %s", topic, reason)
    publish_live_update_from_thread(
        {
            "event_type": event.event_type,
            "event_id": event.id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "backend_event_at": event.created_at.isoformat(),
            "topic": topic,
            "payload": event.payload,
        }
    )
