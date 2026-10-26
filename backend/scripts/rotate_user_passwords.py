"""Interactively rotate every existing local user password.

Run from the backend directory with:
    ..\\.venv\\Scripts\\python.exe -m scripts.rotate_user_passwords

Passwords are read with getpass (terminal echo disabled), validated and hashed
in memory, and are never written to logs or printed. All account hashes are
changed in one transaction after a verified SQLite backup has been made.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.database import SessionLocal


MIN_PASSWORD_LENGTH = 16


def _sqlite_file(database_url: str) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("Password rotation requires the configured file-backed SQLite database")
    path = Path(url.database)
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def create_verified_backup(database_path: Path) -> Path:
    """Create a consistent backup in local app data, outside the synced repo."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        backup_dir = Path(local_app_data) / "CityResponder" / "security_backups"
    else:
        backup_dir = Path.home() / ".local" / "share" / "CityResponder" / "security_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"cityresponder-before-password-rotation-{timestamp}.db"
    if backup_path.exists():
        raise FileExistsError("A backup with the current timestamp already exists")

    with closing(sqlite3.connect(database_path)) as source, closing(
        sqlite3.connect(backup_path)
    ) as target:
        source.backup(target)
    with closing(sqlite3.connect(backup_path)) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        source_counts = _database_counts(database_path)
        backup_counts = _database_counts(backup_path)
    if integrity != "ok" or source_counts != backup_counts:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("SQLite backup verification failed; no accounts were changed")
    return backup_path


def _database_counts(path: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(path)) as connection:
        users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        events = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return users, events


def _read_confirmed_password(
    email: str,
    read_secret: Callable[[str], str],
    forbidden_passwords: tuple[str, ...],
    seen_fingerprints: set[bytes],
) -> str:
    password = read_secret(f"New password for {email}: ")
    confirmation = read_secret(f"Confirm new password for {email}: ")
    if not hmac.compare_digest(password, confirmation):
        raise ValueError("Password confirmation did not match; no accounts were changed")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters; no accounts were changed")
    if len(password) > 1024:
        raise ValueError("Password exceeds the supported maximum; no accounts were changed")
    if any(hmac.compare_digest(password, value) for value in forbidden_passwords):
        raise ValueError("A built-in development password cannot be reused; no accounts were changed")

    fingerprint = hashlib.sha256(password.encode("utf-8")).digest()
    if fingerprint in seen_fingerprints:
        raise ValueError("Each account must receive a distinct password; no accounts were changed")
    seen_fingerprints.add(fingerprint)
    return password


def rotate_accounts(
    db: Session,
    *,
    confirm: Callable[[int], bool],
    read_secret: Callable[[str], str] = getpass.getpass,
    forbidden_passwords: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Rotate every current user's password hash atomically after confirmation."""

    users = list(db.scalars(select(User).order_by(User.id.asc())).all())
    if not users:
        raise ValueError("No user accounts exist; no accounts were changed")
    if not confirm(len(users)):
        raise ValueError("Rotation was not confirmed; no accounts were changed")

    expected_ids = {user.id for user in users}
    hashes: dict[int, str] = {}
    seen_fingerprints: set[bytes] = set()
    for user in users:
        password = _read_confirmed_password(
            user.email,
            read_secret,
            forbidden_passwords,
            seen_fingerprints,
        )
        hashes[user.id] = hash_password(password)
        del password

    current_ids = set(db.scalars(select(User.id)).all())
    if current_ids != expected_ids:
        raise RuntimeError("The account list changed during rotation; no accounts were changed")

    try:
        for user in users:
            user.password_hash = hashes[user.id]
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        hashes.clear()
        seen_fingerprints.clear()

    return tuple(user.email for user in users)


def main() -> int:
    settings = get_settings()
    if settings.environment.strip().lower() not in {"development", "dev"}:
        raise SystemExit("This local rotation utility only runs in development environment")

    database_path = _sqlite_file(settings.database_url)
    db = SessionLocal()
    try:
        users = list(db.scalars(select(User).order_by(User.id.asc())).all())
        if not users:
            raise SystemExit("No user accounts found; nothing to rotate")

        print(f"Accounts to rotate ({len(users)}):")
        for user in users:
            print(f"  ID {user.id}: {user.email} [{user.role.value}; {'active' if user.is_active else 'inactive'}]")
        expected = f"ROTATE ALL {len(users)} PASSWORDS"
        typed = input(f"Type exactly '{expected}' to continue: ")
        if not hmac.compare_digest(typed, expected):
            raise SystemExit("Rotation cancelled; no account was changed")

        backup_path = create_verified_backup(database_path)
        print(f"Verified database backup: {backup_path}")
        rotated = rotate_accounts(
            db,
            confirm=lambda _count: True,
            forbidden_passwords=(settings.dev_seed_password,) if settings.dev_seed_password else (),
        )
        print(f"Password hashes rotated for {len(rotated)} accounts. Passwords were not displayed.")
        print("Restart FastAPI before testing; existing JWTs are invalidated by the rotated JWT secret.")
        return 0
    except KeyboardInterrupt:
        db.rollback()
        print("\nRotation cancelled; no account was changed.")
        return 130
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        print(str(exc))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
