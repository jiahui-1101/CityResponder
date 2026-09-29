"""Internal service for publishing live updates."""

import asyncio
import logging
from asyncio import AbstractEventLoop
from collections.abc import Mapping
from typing import Any

from app.live.manager import live_connection_manager


logger = logging.getLogger(__name__)
_live_event_loop: AbstractEventLoop | None = None


async def publish_live_update(message: Mapping[str, Any]) -> None:
    """Publish a generic JSON update to all connected live clients."""

    await live_connection_manager.broadcast_json(message)


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
