"""Development user seeding for the local authentication foundation."""

from sqlalchemy import select

from app.auth.models import User, UserRole
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.database import SessionLocal


def seed_development_users() -> None:
    """Seed one account per role only when the user table is empty."""

    settings = get_settings()
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).limit(1)) is not None:
            return

        users = (
            (settings.dev_operator_email, UserRole.OPERATOR),
            (settings.dev_firefighter_email, UserRole.FIREFIGHTER),
            (settings.dev_risk_planner_email, UserRole.RISK_PLANNER),
            (settings.dev_admin_email, UserRole.ADMIN),
        )
        password_hash = hash_password(settings.dev_seed_password)
        db.add_all(
            User(email=email.lower(), password_hash=password_hash, role=role)
            for email, role in users
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
