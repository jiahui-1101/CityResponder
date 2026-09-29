"""Reusable JWT authentication dependency."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.core.config import get_settings
from app.core.database import get_db


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_token(token: str, db: Session) -> User:
    """Resolve an active user from a JWT, independent of transport."""

    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise _unauthorized() from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the active user represented by a bearer token."""

    if credentials is None:
        raise _unauthorized()
    return authenticate_token(credentials.credentials, db)


def require_role(required_role: UserRole) -> Callable[..., User]:
    """Require one role, while allowing ADMIN as the universal role."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in {required_role, UserRole.ADMIN}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this resource",
            )
        return current_user

    return dependency


def require_any_role(*allowed_roles: UserRole) -> Callable[..., User]:
    """Require any listed role, while allowing ADMIN as the universal role."""

    allowed = set(allowed_roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed and current_user.role is not UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this resource",
            )
        return current_user

    return dependency


require_authenticated_role = require_any_role(
    UserRole.OPERATOR,
    UserRole.FIREFIGHTER,
    UserRole.RISK_PLANNER,
)
