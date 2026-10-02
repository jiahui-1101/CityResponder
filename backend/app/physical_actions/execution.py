"""Execution adapter for planned physical command sequences."""

import asyncio
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.actuators.service import publish_actuator_command
from app.actuators.ack_waiter import wait_for_actuator_ack
from app.physical_actions.schemas import PhysicalActionCommandSpec
from app.physical_actions.schemas import ActionCategory, ActionType
from app.physical_actions.sequence import PhysicalCommandSequence, SequencePhase
from app.routing.freshness import validate_traffic_command_route_version


class PhysicalCommandExecutionResult(BaseModel):
    """Result of one call to the generic Part 1 command service."""

    phase: SequencePhase
    spec_id: str
    action_category: str
    action_type: str
    target_node_id: str
    route_id: str | None
    route_version: int | None
    command_id: str | None = None
    status: str
    error: str | None = None
    safe_default: bool = False
    attempts: list["PhysicalCommandAttemptResult"] = Field(default_factory=list)
    route_validity_status: str | None = None
    route_stale: bool = False
    route_invalidated: bool = False
    latest_route_version: int | None = None
    was_not_published: bool = False


class PhysicalCommandAttemptResult(BaseModel):
    """One publish/ACK attempt linked to a command specification."""

    phase: SequencePhase
    spec_id: str
    attempt_number: int
    command_id: str | None
    publish_status: str
    ack_status: str
    ack_latency_ms: float | None
    error: str | None
    reason: str | None
    started_at: datetime
    completed_at: datetime
    safe_default: bool = False
    route_validity_status: str | None = None
    latest_route_version: int | None = None
    was_not_published: bool = False


class PhysicalSequenceExecutionResult(BaseModel):
    """Auditable sequence execution result without ACK interpretation."""

    sequence_id: str
    status: str
    route_id: str | None
    route_version: int | None
    command_results: list[PhysicalCommandExecutionResult] = Field(
        default_factory=list
    )
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


async def execute_physical_sequence(
    db: Session,
    sequence: PhysicalCommandSequence,
) -> PhysicalSequenceExecutionResult:
    """Execute planned phases sequentially through the Part 1 command service."""

    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    results: list[PhysicalCommandExecutionResult] = []
    reasons: list[str] = []
    warnings: list[str] = []
    if sequence.status != "planned":
        completed_at = datetime.now(timezone.utc)
        return PhysicalSequenceExecutionResult(
            sequence_id=sequence.sequence_id,
            status="not_executed",
            route_id=sequence.route_id,
            route_version=sequence.route_version,
            command_results=[],
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=(perf_counter() - started_clock) * 1000.0,
            reasons=["physical command sequence is not planned for execution"],
            warnings=list(sequence.warnings),
        )

    for phase in sequence.phases:
        for spec in phase.command_specs:
            result = _execute_one(db, phase.phase, spec)
            results.append(result)
            if result.status == "failed":
                reasons.append(result.error or "physical command execution failed")
                completed_at = datetime.now(timezone.utc)
                return PhysicalSequenceExecutionResult(
                    sequence_id=sequence.sequence_id,
                    status="failed",
                    route_id=sequence.route_id,
                    route_version=sequence.route_version,
                    command_results=results,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=(perf_counter() - started_clock) * 1000.0,
                    reasons=reasons,
                    warnings=warnings + list(sequence.warnings),
                )
        if phase.delay_after_ms:
            await asyncio.sleep(phase.delay_after_ms / 1000.0)

    completed_at = datetime.now(timezone.utc)
    return PhysicalSequenceExecutionResult(
        sequence_id=sequence.sequence_id,
        status="completed",
        route_id=sequence.route_id,
        route_version=sequence.route_version,
        command_results=results,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=(perf_counter() - started_clock) * 1000.0,
        reasons=reasons,
        warnings=warnings + list(sequence.warnings),
    )


def _execute_one(
    db: Session,
    phase: SequencePhase,
    spec: PhysicalActionCommandSpec,
) -> PhysicalCommandExecutionResult:
    try:
        payload: dict[str, Any] = {
            "action_category": spec.action_category.value,
            "action_type": spec.action_type.value,
            "parameters": dict(spec.parameters),
            "spec_id": spec.spec_id,
            "source_recommendation_id": spec.source_recommendation_id,
        }
        if spec.route_id is not None:
            payload["route_id"] = spec.route_id
        if spec.route_version is not None:
            payload["route_version"] = spec.route_version
        command = publish_actuator_command(
            db,
            node_id=spec.target_node_id,
            command_type="PHYSICAL_ACTION",
            payload=payload,
        )
        return PhysicalCommandExecutionResult(
            phase=phase,
            spec_id=spec.spec_id,
            action_category=spec.action_category.value,
            action_type=spec.action_type.value,
            target_node_id=spec.target_node_id,
            route_id=spec.route_id,
            route_version=spec.route_version,
            command_id=command.get("command_id"),
            status="published",
            safe_default=spec.safe_default,
        )
    except Exception as exc:
        return PhysicalCommandExecutionResult(
            phase=phase,
            spec_id=spec.spec_id,
            action_category=spec.action_category.value,
            action_type=spec.action_type.value,
            target_node_id=spec.target_node_id,
            route_id=spec.route_id,
            route_version=spec.route_version,
            status="failed",
            error=str(exc),
            safe_default=spec.safe_default,
        )


async def execute_ack_gated_sequence(
    db: Session,
    sequence: PhysicalCommandSequence,
) -> PhysicalSequenceExecutionResult:
    """Execute normal commands with one retry and one non-recursive fallback."""

    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    results: list[PhysicalCommandExecutionResult] = []
    if sequence.status != "planned":
        return _sequence_result(
            sequence,
            "not_executed",
            results,
            started_at,
            started_clock,
            ["physical command sequence is not planned for execution"],
        )

    for phase in sequence.phases:
        for spec in phase.command_specs:
            result = await _execute_normal_with_ack(db, phase.phase, spec)
            results.append(result)
            if result.status in {"acknowledged", "acknowledged_after_retry"}:
                continue
            if result.status == "stale_route_version":
                return _sequence_result(
                    sequence,
                    "traffic_command_invalidated",
                    results,
                    started_at,
                    started_clock,
                    ["stale traffic command was not published"],
                )
            if result.status != "ack_timeout_exhausted":
                return _sequence_result(
                    sequence,
                    "execution_failed",
                    results,
                    started_at,
                    started_clock,
                    [result.error or "normal command execution failed before ACK timeout"],
                )
            fallback_results = await _execute_safe_defaults(
                db,
                failed_spec=spec,
                source_phase=phase.phase,
            )
            results.extend(fallback_results)
            fallback_failed = any(
                fallback.status == "failed" for fallback in fallback_results
            )
            return _sequence_result(
                sequence,
                "safe_default_partial_failure" if fallback_failed else "safe_default_applied",
                results,
                started_at,
                started_clock,
                ["normal command failed after two attempts"],
            )
        if phase.delay_after_ms:
            await asyncio.sleep(phase.delay_after_ms / 1000.0)
    status = (
        "completed_after_retry"
        if any(result.status == "acknowledged_after_retry" for result in results)
        else "completed"
    )
    return _sequence_result(
        sequence,
        status,
        results,
        started_at,
        started_clock,
        [],
    )


async def _execute_normal_with_ack(
    db: Session,
    phase: SequencePhase,
    spec: PhysicalActionCommandSpec,
) -> PhysicalCommandExecutionResult:
    attempts: list[PhysicalCommandAttemptResult] = []
    last_command_id: str | None = None
    for attempt_number in (1, 2):
        attempt_started = datetime.now(timezone.utc)
        attempt_clock = perf_counter()
        route_check = None
        if not spec.safe_default and spec.action_category is ActionCategory.TRAFFIC:
            route_check = validate_traffic_command_route_version(
                db,
                spec,
                command_id=last_command_id,
            )
            if not route_check.valid_for_execution:
                stale_status = (
                    "stale_route_version"
                    if route_check.stale
                    else "traffic_route_invalid_configuration"
                )
                attempt = PhysicalCommandAttemptResult(
                    phase=phase,
                    spec_id=spec.spec_id,
                    attempt_number=attempt_number,
                    command_id=last_command_id,
                    publish_status="not_published",
                    ack_status="not_waited",
                    ack_latency_ms=None,
                    error=route_check.reason,
                    reason=route_check.reason,
                    started_at=attempt_started,
                    completed_at=datetime.now(timezone.utc),
                    route_validity_status=route_check.status,
                    latest_route_version=route_check.latest_route_version,
                    was_not_published=True,
                )
                return PhysicalCommandExecutionResult(
                    phase=phase,
                    spec_id=spec.spec_id,
                    action_category=spec.action_category.value,
                    action_type=spec.action_type.value,
                    target_node_id=spec.target_node_id,
                    route_id=spec.route_id,
                    route_version=spec.route_version,
                    command_id=last_command_id,
                    status=stale_status,
                    error=route_check.reason,
                    attempts=[attempt],
                    route_validity_status=route_check.status,
                    route_stale=route_check.stale,
                    route_invalidated=route_check.invalidated,
                    latest_route_version=route_check.latest_route_version,
                    was_not_published=True,
                )
        try:
            payload = _command_payload(spec, attempt_number, last_command_id)
            command = publish_actuator_command(
                db,
                node_id=spec.target_node_id,
                command_type="PHYSICAL_ACTION",
                payload=payload,
            )
            command_id = command.get("command_id")
            last_command_id = command_id
            ack = await wait_for_actuator_ack(command_id, spec.target_node_id)
            attempt = PhysicalCommandAttemptResult(
                phase=phase,
                spec_id=spec.spec_id,
                attempt_number=attempt_number,
                command_id=command_id,
                publish_status="published",
                ack_status=ack.status,
                ack_latency_ms=ack.latency_ms,
                error=None if ack.ack_received else "actuator ACK timeout",
                reason="matching actuator ACK received" if ack.ack_received else "ACTUATOR_ACK_TIMEOUT",
                started_at=attempt_started,
                completed_at=ack.completed_at,
                route_validity_status=(route_check.status if route_check else None),
                latest_route_version=(
                    route_check.latest_route_version if route_check else None
                ),
            )
            attempts.append(attempt)
            if ack.ack_received:
                return PhysicalCommandExecutionResult(
                    phase=phase,
                    spec_id=spec.spec_id,
                    action_category=spec.action_category.value,
                    action_type=spec.action_type.value,
                    target_node_id=spec.target_node_id,
                    route_id=spec.route_id,
                    route_version=spec.route_version,
                    command_id=command_id,
                    status=(
                        "acknowledged_after_retry"
                        if attempt_number == 2
                        else "acknowledged"
                    ),
                    safe_default=False,
                    attempts=attempts,
                    route_validity_status=(route_check.status if route_check else None),
                    latest_route_version=(
                        route_check.latest_route_version if route_check else None
                    ),
                )
        except Exception as exc:
            attempts.append(
                PhysicalCommandAttemptResult(
                    phase=phase,
                    spec_id=spec.spec_id,
                    attempt_number=attempt_number,
                    command_id=last_command_id,
                    publish_status="failed",
                    ack_status="not_waited",
                    ack_latency_ms=None,
                    error=str(exc),
                    reason="publish failure; retry is not attempted",
                    started_at=attempt_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return PhysicalCommandExecutionResult(
                phase=phase,
                spec_id=spec.spec_id,
                action_category=spec.action_category.value,
                action_type=spec.action_type.value,
                target_node_id=spec.target_node_id,
                route_id=spec.route_id,
                route_version=spec.route_version,
                command_id=last_command_id,
                status="execution_failed",
                error=str(exc),
                attempts=attempts,
            )
    return PhysicalCommandExecutionResult(
        phase=phase,
        spec_id=spec.spec_id,
        action_category=spec.action_category.value,
        action_type=spec.action_type.value,
        target_node_id=spec.target_node_id,
        route_id=spec.route_id,
        route_version=spec.route_version,
        command_id=last_command_id,
        status="ack_timeout_exhausted",
        error="no actuator ACK after two attempts",
        attempts=attempts,
    )


async def _execute_safe_defaults(
    db: Session,
    *,
    failed_spec: PhysicalActionCommandSpec,
    source_phase: SequencePhase,
) -> list[PhysicalCommandExecutionResult]:
    specs = build_safe_default_specs(
        target_node_id=failed_spec.target_node_id,
        route_id=failed_spec.route_id,
        route_version=failed_spec.route_version,
        source_recommendation_id=failed_spec.source_recommendation_id,
        audit_references=failed_spec.audit_references,
        trigger_reason="ACTUATOR_ACK_TIMEOUT",
    )
    return [
        await _execute_safe_default_once(db, source_phase, spec)
        for spec in specs
    ]


def build_safe_default_specs(
    *,
    target_node_id: str,
    route_id: str | None = None,
    route_version: int | None = None,
    source_recommendation_id: str | None = None,
    audit_references: list[Any] | None = None,
    trigger_reason: str,
) -> list[PhysicalActionCommandSpec]:
    """Build exactly the source-backed safe-default action set."""

    return [
        PhysicalActionCommandSpec(
            action_category=category,
            action_type=action_type,
            target_node_id=target_node_id,
            route_id=route_id,
            route_version=route_version,
            source_recommendation_id=source_recommendation_id,
            reasons=[trigger_reason],
            audit_references=list(audit_references or []),
            safe_default=True,
        )
        for category, action_type in (
            (ActionCategory.TRAFFIC, ActionType.ALL_RED),
            (ActionCategory.GATE, ActionType.CLOSE),
            (ActionCategory.BUZZER, ActionType.ON),
        )
    ]


def build_cancellation_specs(
    *,
    target_node_id: str,
    route_id: str | None = None,
    route_version: int | None = None,
    source_recommendation_id: str | None = None,
    audit_references: list[Any] | None = None,
    trigger_reason: str,
) -> list[PhysicalActionCommandSpec]:
    """Build exactly the action set to reverse/cancel dispatch."""
    return [
        PhysicalActionCommandSpec(
            action_category=category,
            action_type=action_type,
            target_node_id=target_node_id,
            route_id=route_id,
            route_version=route_version,
            source_recommendation_id=source_recommendation_id,
            reasons=[trigger_reason],
            audit_references=list(audit_references or []),
            safe_default=True,
        )
        for category, action_type in (
            (ActionCategory.TRAFFIC, ActionType.OFF),
            (ActionCategory.GATE, ActionType.CLOSE),
            (ActionCategory.BUZZER, ActionType.OFF),
        )
    ]


async def execute_safe_default_specs_once(
    db: Session,
    specs: list[PhysicalActionCommandSpec],
    *,
    sequence_id: str,
    route_id: str | None,
    route_version: int | None,
    warnings: list[str] | None = None,
) -> PhysicalSequenceExecutionResult:
    """Execute supplied safe defaults once, with no retry or recursive fallback."""

    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    results = [
        await _execute_safe_default_once(db, SequencePhase.SAFETY_TRANSITION, spec)
        for spec in specs
    ]
    failed = any(result.status == "failed" for result in results)
    return PhysicalSequenceExecutionResult(
        sequence_id=sequence_id,
        status="safe_default_partial_failure" if failed else "safe_default_applied",
        route_id=route_id,
        route_version=route_version,
        command_results=results,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        duration_ms=(perf_counter() - started_clock) * 1000.0,
        reasons=["safe defaults executed once; no retry permitted"],
        warnings=list(warnings or []),
    )


async def _execute_safe_default_once(
    db: Session,
    phase: SequencePhase,
    spec: PhysicalActionCommandSpec,
) -> PhysicalCommandExecutionResult:
    started = datetime.now(timezone.utc)
    try:
        command = publish_actuator_command(
            db,
            node_id=spec.target_node_id,
            command_type="PHYSICAL_ACTION",
            payload=_command_payload(spec, 1, None),
        )
        command_id = command.get("command_id")
        ack = await wait_for_actuator_ack(command_id, spec.target_node_id)
        attempt = PhysicalCommandAttemptResult(
            phase=phase,
            spec_id=spec.spec_id,
            attempt_number=1,
            command_id=command_id,
            publish_status="published",
            ack_status=ack.status,
            ack_latency_ms=ack.latency_ms,
            error=None if ack.ack_received else "safe-default ACK timeout",
            reason="safe default; no retry permitted",
            started_at=started,
            completed_at=ack.completed_at,
            safe_default=True,
        )
        return PhysicalCommandExecutionResult(
            phase=phase,
            spec_id=spec.spec_id,
            action_category=spec.action_category.value,
            action_type=spec.action_type.value,
            target_node_id=spec.target_node_id,
            route_id=spec.route_id,
            route_version=spec.route_version,
            command_id=command_id,
            status="acknowledged" if ack.ack_received else "failed",
            error=attempt.error,
            safe_default=True,
            attempts=[attempt],
        )
    except Exception as exc:
        return PhysicalCommandExecutionResult(
            phase=phase,
            spec_id=spec.spec_id,
            action_category=spec.action_category.value,
            action_type=spec.action_type.value,
            target_node_id=spec.target_node_id,
            route_id=spec.route_id,
            route_version=spec.route_version,
            status="failed",
            error=str(exc),
            safe_default=True,
            attempts=[
                PhysicalCommandAttemptResult(
                    phase=phase,
                    spec_id=spec.spec_id,
                    attempt_number=1,
                    command_id=None,
                    publish_status="failed",
                    ack_status="not_waited",
                    ack_latency_ms=None,
                    error=str(exc),
                    reason="safe default publish failed; no retry permitted",
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                    safe_default=True,
                )
            ],
        )


def _command_payload(
    spec: PhysicalActionCommandSpec,
    attempt_number: int,
    retry_of_command_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action_category": spec.action_category.value,
        "action_type": spec.action_type.value,
        "parameters": dict(spec.parameters),
        "spec_id": spec.spec_id,
        "source_recommendation_id": spec.source_recommendation_id,
        "attempt_number": attempt_number,
        "safe_default": spec.safe_default,
    }
    if retry_of_command_id is not None:
        payload["retry_of_command_id"] = retry_of_command_id
    if spec.route_id is not None:
        payload["route_id"] = spec.route_id
    if spec.route_version is not None:
        payload["route_version"] = spec.route_version
    return payload


def _sequence_result(
    sequence: PhysicalCommandSequence,
    status: str,
    results: list[PhysicalCommandExecutionResult],
    started_at: datetime,
    started_clock: float,
    reasons: list[str],
) -> PhysicalSequenceExecutionResult:
    completed_at = datetime.now(timezone.utc)
    return PhysicalSequenceExecutionResult(
        sequence_id=sequence.sequence_id,
        status=status,
        route_id=sequence.route_id,
        route_version=sequence.route_version,
        command_results=results,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=(perf_counter() - started_clock) * 1000.0,
        reasons=reasons,
        warnings=list(sequence.warnings),
    )
