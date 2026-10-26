"""Per-command actuator ACK correlation with a fixed 500 ms timeout."""

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from time import monotonic, perf_counter
from typing import Any

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
ACK_TIMEOUT_MS = 500
_MAX_CACHED_ACKS = 1024


class ActuatorAckResult(BaseModel):
    """Outcome of waiting for one actuator-side ACK."""

    command_id: str
    target_node_id: str
    status: str
    ack_received: bool
    ack_payload: dict[str, Any] | None
    ack_timestamp: datetime | None
    timeout_ms: int = ACK_TIMEOUT_MS
    latency_ms: float | None
    started_at: datetime
    completed_at: datetime
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class _PendingAck:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        future: asyncio.Future[dict[str, Any]],
        target_node_id: str,
    ):
        self.loop = loop
        self.future = future
        self.target_node_id = target_node_id


_lock = Lock()
_pending: dict[str, _PendingAck] = {}
_cached: OrderedDict[str, tuple[str, dict[str, Any], datetime, float, bool]] = OrderedDict()
_timed_out: OrderedDict[str, float] = OrderedDict()


async def wait_for_actuator_ack(
    command_id: str,
    target_node_id: str,
    timeout_ms: int = ACK_TIMEOUT_MS,
) -> ActuatorAckResult:
    """Wait for the exact command ACK, including ACKs received before registration."""

    if timeout_ms != ACK_TIMEOUT_MS:
        raise ValueError("actuator ACK timeout is fixed at 500 ms")
    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    cached = _register_waiter(command_id, target_node_id, loop, future)
    if cached is not None:
        payload, late = cached
        return _acknowledged_result(
            command_id,
            target_node_id,
            payload,
            started_at,
            started_clock,
            late=late,
        )

    try:
        payload = await asyncio.wait_for(asyncio.shield(future), timeout_ms / 1000.0)
    except asyncio.TimeoutError:
        _remove_waiter(command_id, future)
        _remember_timeout(command_id)
        completed_at = datetime.now(timezone.utc)
        return ActuatorAckResult(
            command_id=command_id,
            target_node_id=target_node_id,
            status="timeout",
            ack_received=False,
            ack_payload=None,
            ack_timestamp=None,
            latency_ms=None,
            started_at=started_at,
            completed_at=completed_at,
            reasons=["no matching actuator ACK received within 500 ms"],
        )
    except asyncio.CancelledError:
        _remove_waiter(command_id, future)
        raise
    _complete_waiter(command_id, future)
    return _acknowledged_result(
        command_id,
        target_node_id,
        payload,
        started_at,
        started_clock,
        late=_was_late(command_id),
    )


def notify_actuator_ack(
    command_id: str,
    node_id: str,
    payload: dict[str, Any],
    ack_timestamp: datetime,
) -> None:
    """Notify a waiter and cache the ACK for an ACK-before-wait race."""

    if not _is_terminal(payload):
        return
    with _lock:
        received_at = monotonic()
        if command_id in _cached:
            return
        late = command_id in _timed_out
        _cached[command_id] = (node_id, dict(payload), ack_timestamp, received_at, late)
        _cached.move_to_end(command_id)
        _trim_timed_out()
        while len(_cached) > _MAX_CACHED_ACKS:
            _cached.popitem(last=False)
        pending = _pending.get(command_id)
        if pending is None:
            return
        if pending.target_node_id != node_id:
            return
        if pending.loop.is_closed():
            _pending.pop(command_id, None)
            return
        # A timed-out command can receive its valid ACK while the safe,
        # same-ID retry is already waiting. Preserve that late classification.
        pending.loop.call_soon_threadsafe(_resolve_pending, pending.future, node_id, payload)


def _register_waiter(
    command_id: str,
    target_node_id: str,
    loop: asyncio.AbstractEventLoop,
    future: asyncio.Future[dict[str, Any]],
) -> tuple[dict[str, Any], bool] | None:
    with _lock:
        cached = _cached.pop(command_id, None)
        if cached is not None:
            node_id, payload, _timestamp, _received_at, late = cached
            if node_id == target_node_id:
                _timed_out.pop(command_id, None)
                return payload, late
        _pending[command_id] = _PendingAck(loop, future, target_node_id)
    return None


def _resolve_pending(
    future: asyncio.Future[dict[str, Any]],
    node_id: str,
    payload: dict[str, Any],
) -> None:
    if not future.done():
        future.set_result(dict(payload))


def _remove_waiter(command_id: str, future: asyncio.Future[dict[str, Any]]) -> None:
    with _lock:
        pending = _pending.get(command_id)
        if pending is not None and pending.future is future:
            _pending.pop(command_id, None)


def _complete_waiter(command_id: str, future: asyncio.Future[dict[str, Any]]) -> None:
    """Release a satisfied waiter and its already-consumed ACK cache entry."""

    with _lock:
        pending = _pending.get(command_id)
        if pending is not None and pending.future is future:
            _pending.pop(command_id, None)
        _cached.pop(command_id, None)


def _acknowledged_result(
    command_id: str,
    target_node_id: str,
    payload: dict[str, Any],
    started_at: datetime,
    started_clock: float,
    *,
    late: bool = False,
) -> ActuatorAckResult:
    ack_timestamp = _payload_timestamp(payload)
    completed_at = datetime.now(timezone.utc)
    return ActuatorAckResult(
        command_id=command_id,
        target_node_id=target_node_id,
        status=(
            "late_acknowledged"
            if late and _is_success(payload)
            else "late_failed"
            if late
            else "acknowledged"
            if _is_success(payload)
            else "failed"
        ),
        ack_received=True,
        ack_payload=dict(payload),
        ack_timestamp=ack_timestamp,
        latency_ms=(perf_counter() - started_clock) * 1000.0,
        started_at=started_at,
        completed_at=completed_at,
    )


def _payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    value = payload.get("timestamp")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Actuator ACK timestamp is not valid ISO-8601")
    return None


def _is_terminal(payload: dict[str, Any]) -> bool:
    """A receipt is observable but does not finish the ACK wait."""

    return payload.get("stage") != "received" and payload.get("status") != "RECEIVED"


def _is_success(payload: dict[str, Any]) -> bool:
    """Only an execution report represents a successful command ACK."""

    return payload.get("status") in {"ACK", "EXECUTED"} and payload.get("stage") != "failed"


def _remember_timeout(command_id: str) -> None:
    with _lock:
        _timed_out[command_id] = monotonic()
        _timed_out.move_to_end(command_id)
        _trim_timed_out()


def _was_late(command_id: str) -> bool:
    with _lock:
        late = command_id in _timed_out
        _timed_out.pop(command_id, None)
        return late


def _trim_timed_out() -> None:
    while len(_timed_out) > _MAX_CACHED_ACKS:
        _timed_out.popitem(last=False)


def clear_ack_waiter_state() -> None:
    """Reset in-memory correlation state for isolated tests and shutdowns."""

    with _lock:
        _pending.clear()
        _cached.clear()
        _timed_out.clear()
