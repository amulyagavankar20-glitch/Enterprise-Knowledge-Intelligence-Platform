import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.db.models import User
from app.schemas import RegisterRequest, TokenResponse, UserResponse
from app.services.auth import (
    create_access_token,
    ensure_auth_configured,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.rate_limit import enforce_rate_limit
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, scope="register", limit=5)
    ensure_auth_configured()
    email = payload.email.strip().casefold()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="Invalid email address.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role="member",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    record_audit(
        db,
        actor_id=user.id,
        action="user.registered",
        resource_type="user",
        resource_id=str(user.id),
    )
    return UserResponse(id=str(user.id), email=user.email, role=user.role)


@router.post("/token", response_model=TokenResponse)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, scope="login", limit=10)
    ensure_auth_configured()
    email = form.username.strip().casefold()
    if len(email) > 320 or len(form.password) > 128:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.email == email).first()
    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.password_hash)
    ):
        record_audit(
            db,
            actor_id=None,
            action="auth.login_failed",
            resource_type="authentication",
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)
    record_audit(
        db,
        actor_id=user.id,
        action="auth.login_succeeded",
        resource_type="authentication",
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def current_user_profile(user: User = Depends(get_current_user)):
    """Return only the current authenticated user's profile and role."""
    return UserResponse(id=str(user.id), email=user.email, role=user.role)
