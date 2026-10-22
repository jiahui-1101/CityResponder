"""SQLAlchemy models for generic system and audit events."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    """Immutable event history record."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    human_readable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class IncidentTransitionClaim(Base):
    """Insert-only database lock for the single ALERT-to-CONFIRMED winner."""

    __tablename__ = "incident_transition_claims"

    incident_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    winner_type: Mapped[str] = mapped_column(String(50), nullable=False)
    winner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
