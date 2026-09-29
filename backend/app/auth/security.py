"""Password hashing and JWT token helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.auth.models import User
from app.core.config import get_settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return a secure password hash."""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against its stored hash."""

    return password_hasher.verify(password, password_hash)


def create_access_token(user: User) -> str:
    """Create a signed JWT containing only non-secret user claims."""

    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    claims: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "exp": expires_at,
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
