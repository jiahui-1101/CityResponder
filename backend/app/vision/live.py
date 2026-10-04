"""Shared, on-demand annotated vision frames for the local demo UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Condition, Thread
from time import monotonic
from typing import Any, Callable

from app.vision.pipeline import IntegratedVisionPipeline


logger = logging.getLogger(__name__)
# Keep the warmed models available across brief role/page transitions.  The
# worker still releases the camera after a real idle period, but a ten-second
# timeout caused repeated 14-second cold starts during normal demo navigation.
IDLE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class LiveVisionFrame:
    jpeg: bytes
    metadata: dict[str, Any]
    generated_at: datetime
    sequence: int


class SharedVisionFrameService:
    """Own exactly one camera/inference pipeline while viewers are active."""

    def __init__(
        self,
        pipeline_factory: Callable[[], IntegratedVisionPipeline] = IntegratedVisionPipeline,
        *,
        idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._pipeline_factory = pipeline_factory
        self._idle_timeout_seconds = idle_timeout_seconds
        self._condition = Condition()
        self._thread: Thread | None = None
        self._latest: LiveVisionFrame | None = None
        self._last_error: str | None = None
        self._last_access = 0.0
        self._sequence = 0
        self._state = "idle"

    def start(self) -> None:
        """Start one background pipeline without blocking an API request."""

        with self._condition:
            self._last_access = monotonic()
            if self._thread is not None and self._thread.is_alive():
                return
            self._last_error = None
            self._state = "initializing"
            self._thread = Thread(
                target=self._run,
                name="cityresponder-shared-vision",
                daemon=True,
            )
            self._thread.start()

    def status(self) -> tuple[str, str | None]:
        """Return the real shared-pipeline lifecycle state for UI health."""

        with self._condition:
            return self._state, self._last_error

    def latest(self, *, timeout_seconds: float = 0.25) -> LiveVisionFrame:
        """Start the shared worker if necessary and wait for one real frame."""

        self.start()
        with self._condition:
            self._last_access = monotonic()
            cached = self._latest
            # Once a real frame exists, never hold an API worker waiting for
            # another expensive inference. The timestamp lets the UI mark the
            # retained real frame stale while the shared worker updates it.
            if cached is not None:
                return cached
            self._condition.wait_for(
                lambda: self._latest is not None or self._last_error is not None,
                timeout=timeout_seconds,
            )
            self._last_access = monotonic()
            if self._latest is not None:
                return self._latest
            if self._last_error:
                raise RuntimeError(self._last_error)
            raise TimeoutError("Timed out waiting for the shared vision pipeline")

    def stop(self) -> None:
        """Request clean shutdown; used by application lifespan and tests."""

        with self._condition:
            self._last_access = float("-inf")
            self._condition.notify_all()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(1.0, self._idle_timeout_seconds + 1.0))

    def _run(self) -> None:
        pipeline: IntegratedVisionPipeline | None = None
        try:
            pipeline = self._pipeline_factory()
            while True:
                iteration_started = monotonic()
                with self._condition:
                    if monotonic() - self._last_access > self._idle_timeout_seconds:
                        return
                processed = pipeline.process_one(publish=True)
                jpeg, metadata = pipeline.render_annotated_frame(processed)
                with self._condition:
                    self._sequence += 1
                    self._latest = LiveVisionFrame(
                        jpeg=jpeg,
                        metadata=metadata,
                        generated_at=datetime.now(timezone.utc),
                        sequence=self._sequence,
                    )
                    self._last_error = None
                    self._state = "ready"
                    self._condition.notify_all()
                    target_fps = max(
                        pipeline.config.detection_target_fps,
                        pipeline.config.segmentation_target_fps,
                    )
                    remaining = max(
                        0.0,
                        (1.0 / target_fps) - (monotonic() - iteration_started),
                    ) if target_fps > 0 else 0.0
                    if remaining:
                        self._condition.wait(timeout=remaining)
        except Exception as exc:
            logger.exception("Shared vision worker stopped")
            with self._condition:
                self._last_error = str(exc)
                self._state = "error"
                self._condition.notify_all()
        finally:
            if pipeline is not None:
                pipeline.close()
            with self._condition:
                self._thread = None
                if self._state != "error":
                    self._state = "idle"
                self._condition.notify_all()


shared_vision_frames = SharedVisionFrameService()
