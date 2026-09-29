"""Read-only API schema for immutable events."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    """Serialized immutable event returned by read-only endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    entity_type: str
    entity_id: str
    reason_code: str | None
    human_readable_reason: str | None
    payload: dict[str, Any]
    created_at: datetime
