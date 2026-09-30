"""Binary storage abstraction for explicitly selected evidence only."""

from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import get_settings


class EvidenceFrameStore(Protocol):
    def store(self, evidence_id: str, content_type: str, data: bytes) -> str: ...
    def retrieve(self, evidence_id: str) -> tuple[Path, str] | None: ...
    def exists(self, evidence_id: str) -> bool: ...


class LocalEvidenceFrameStore:
    """Prototype convention: controlled app-data directory, generated IDs only."""

    _extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

    def __init__(self, root: str | Path | None = None, max_bytes: int | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.evidence_storage_dir).resolve()
        self.max_bytes = max_bytes or settings.evidence_max_file_size_bytes

    def store(self, evidence_id: str, content_type: str, data: bytes) -> str:
        if content_type not in self._extensions:
            raise ValueError("unsupported evidence image content type")
        if len(data) > self.max_bytes:
            raise ValueError(f"evidence image exceeds implementation safety limit of {self.max_bytes} bytes")
        try:
            UUID(evidence_id)
        except ValueError:
            raise ValueError("evidence ID must be a generated UUID") from None
        self.root.mkdir(parents=True, exist_ok=True)
        path = (self.root / f"{evidence_id}{self._extensions[content_type]}").resolve()
        if self.root not in path.parents:
            raise ValueError("invalid evidence storage path")
        path.write_bytes(data)
        return f"incident_evidence/{evidence_id}{self._extensions[content_type]}"

    def retrieve(self, evidence_id: str) -> tuple[Path, str] | None:
        try:
            UUID(evidence_id)
        except ValueError:
            return None
        for content_type, extension in self._extensions.items():
            path = (self.root / f"{evidence_id}{extension}").resolve()
            if self.root in path.parents and path.is_file():
                return path, content_type
        return None

    def exists(self, evidence_id: str) -> bool:
        return self.retrieve(evidence_id) is not None


def new_evidence_id() -> str:
    return str(uuid4())
