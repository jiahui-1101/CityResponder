"""ADMIN-only local user management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.models import User, UserRole
from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.auth.security import hash_password
from app.core.database import get_db


router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_dependency = Depends(require_role(UserRole.ADMIN))


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = admin_dependency,
) -> list[UserRead]:
    """List local users without exposing password hashes."""

    return list(db.scalars(select(User).order_by(User.id.asc())).all())


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = admin_dependency,
) -> User:
    """Create a local user with a securely hashed password."""

    email = request.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        email=email,
        password_hash=hash_password(request.password),
        role=request.role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        ) from None
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    request: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = admin_dependency,
) -> User:
    """Change a user's role or active state."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    db.commit()
    db.refresh(user)
    return user
