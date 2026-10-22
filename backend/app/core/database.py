"""SQLite engine and session infrastructure for the backend."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for future append-only and domain models."""


def ensure_database_directory(database_url: str) -> None:
    """Create the parent directory for a file-backed SQLite database."""

    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


def initialize_database() -> None:
    """Create configured tables and append-only event-store protections."""

    from app.auth.models import User  # noqa: F401
    from app.events.models import Event  # noqa: F401

    ensure_database_directory(settings.database_url)
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        # Read models project the append-only event stream by type/entity and
        # newest timestamp. These indexes keep live dashboards responsive as
        # high-rate sensor telemetry grows; they do not mutate event records.
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_events_created_at_id "
            "ON events (created_at DESC, id DESC)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_events_type_created_at_id "
            "ON events (event_type, created_at DESC, id DESC)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_events_entity_created_at_id "
            "ON events (entity_type, entity_id, created_at DESC, id DESC)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_events_type_entity_created_at_id "
            "ON events (event_type, entity_type, entity_id, created_at DESC, id DESC)"
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_event_update
            BEFORE UPDATE ON events
            BEGIN
                SELECT RAISE(ABORT, 'event records are append-only');
            END;
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_event_delete
            BEFORE DELETE ON events
            BEGIN
                SELECT RAISE(ABORT, 'event records are append-only');
            END;
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_incident_transition_claim_update
            BEFORE UPDATE ON incident_transition_claims
            BEGIN
                SELECT RAISE(ABORT, 'incident transition claims are insert-only');
            END;
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_incident_transition_claim_delete
            BEFORE DELETE ON incident_transition_claims
            BEGIN
                SELECT RAISE(ABORT, 'incident transition claims are insert-only');
            END;
            """
        )


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it after use."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
