"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.login_rate_limit import login_rate_limiter
from app.auth.models import User
from app.auth.schemas import LoginRequest, TokenResponse, UserRead
from app.auth.security import create_access_token, verify_password
from app.core.database import get_db


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a local user and issue a JWT access token."""

    email = request.email.strip().lower()
    retry_after = login_rate_limiter.retry_after(email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(request.password, user.password_hash):
        login_rate_limiter.record_failure(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    login_rate_limiter.reset(email)
    return TokenResponse(access_token=create_access_token(user))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's public profile."""

    return current_user
