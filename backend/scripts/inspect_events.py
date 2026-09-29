"""Print recent immutable events from the configured SQLite store."""

import argparse
import json
from typing import Any

from app.core.database import SessionLocal, initialize_database
from app.events.repository import get_recent_events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-type", help="Filter by event type")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of events to print (default: 20)",
    )
    return parser.parse_args()


def serialize_event(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "reason_code": event.reason_code,
        "human_readable_reason": event.human_readable_reason,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be greater than zero")

    initialize_database()
    db = SessionLocal()
    try:
        events = get_recent_events(db, limit=args.limit, event_type=args.event_type)
        print(json.dumps([serialize_event(event) for event in events], indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
