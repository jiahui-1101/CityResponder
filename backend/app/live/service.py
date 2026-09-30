"""Internal service for publishing live updates."""

import asyncio
import logging
from datetime import datetime, timezone
from asyncio import AbstractEventLoop
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from app.live.manager import live_connection_manager


logger = logging.getLogger(__name__)
_live_event_loop: AbstractEventLoop | None = None


def _normalize_utc_timestamp(value: Any) -> str | None:
    """Normalize an ISO timestamp for cross-clock diagnostics."""

    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat()


async def publish_live_update(message: Mapping[str, Any]) -> None:
    """Publish a generic JSON update to all connected live clients."""

    enriched = dict(message)
    enriched.setdefault("event_id", str(uuid4()))
    enriched.setdefault("broadcast_at", datetime.now(timezone.utc).isoformat())
    if "backend_event_at" in enriched:
        normalized = _normalize_utc_timestamp(enriched["backend_event_at"])
        if normalized is not None:
            enriched["backend_event_at"] = normalized
    else:
        payload = enriched.get("payload")
        if isinstance(payload, Mapping):
            for key in ("timestamp", "action_timestamp", "evaluated_at", "created_at", "calculated_at", "stored_at"):
                value = payload.get(key)
                normalized = _normalize_utc_timestamp(value)
                if normalized is not None:
                    enriched["backend_event_at"] = normalized
                    break
    await live_connection_manager.broadcast_json(enriched)


def set_live_event_loop(loop: AbstractEventLoop) -> None:
    """Set the application loop used by MQTT worker callbacks."""

    global _live_event_loop
    _live_event_loop = loop


def clear_live_event_loop() -> None:
    """Clear the application loop during shutdown."""

    global _live_event_loop
    _live_event_loop = None


def publish_live_update_from_thread(message: Mapping[str, Any]) -> None:
    """Schedule a live update safely from a synchronous MQTT callback."""

    loop = _live_event_loop
    if loop is None or not loop.is_running():
        logger.warning("Live event loop unavailable; update was not broadcast")
        return

    try:
        future = asyncio.run_coroutine_threadsafe(publish_live_update(message), loop)
        future.add_done_callback(_log_publish_failure)
    except Exception:
        logger.exception("Failed to schedule live update")


def _log_publish_failure(future: Any) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("Live update failed")
