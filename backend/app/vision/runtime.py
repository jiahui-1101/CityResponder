"""In-process observational health for the integrated vision runner."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock


@dataclass(frozen=True)
class VisionRuntimeSnapshot:
    status: str
    last_seen: datetime | None
    detail: str


class VisionRuntimeHealth:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = VisionRuntimeSnapshot(
            status="unknown",
            last_seen=None,
            detail="Integrated vision pipeline has not processed a frame",
        )

    def success(self, frame_id: str) -> None:
        with self._lock:
            self._snapshot = VisionRuntimeSnapshot(
                status="available",
                last_seen=datetime.now(timezone.utc),
                detail=f"Latest integrated frame: {frame_id}",
            )

    def failure(self, detail: str) -> None:
        with self._lock:
            self._snapshot = VisionRuntimeSnapshot(
                status="unavailable",
                last_seen=datetime.now(timezone.utc),
                detail=detail,
            )

    def snapshot(self) -> VisionRuntimeSnapshot:
        with self._lock:
            return self._snapshot


vision_runtime_health = VisionRuntimeHealth()
