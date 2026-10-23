"""Auth API router v1: register, login, logout and account settings (cookie-based sessions)."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DbDep, OwnerDep, UserIdDep, clear_cookie, set_cookie
from app.core.config import get_settings
from app.models.db_models import User
from app.schemas.api_schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    GuestQuotaResponse,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.auth.accounts import claim_guest_data, claim_legacy_data, delete_user_account, is_first_user
from app.services.auth.guest_quota import get_quota
from app.services.auth.security import create_access_token, hash_password, session_lifetime, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_TAKEN = "Email sudah terdaftar. Silakan masuk."
_BAD_LOGIN = "Email atau password salah."


def _start_session(response: Response, user: User, remember: bool) -> None:
    """Ganti cookie tamu browser ini dengan cookie login."""
    auth = get_settings().auth
    lifetime = session_lifetime(remember)
    set_cookie(response, auth.session_cookie, create_access_token(user.id, lifetime), lifetime)
    clear_cookie(response, auth.guest_cookie)


def _verified_user(db: Session, user_id: str, password: str, detail: str) -> User:
    user = db.get(User, user_id)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail=detail)
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: RegisterRequest, request: Request, response: Response, db: DbDep):
    email = data.email.lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
    first = is_first_user(db)
    user = User(email=email, name=data.name, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail=_EMAIL_TAKEN) from e
    if first:
        claim_legacy_data(db, user.id)
    claim_guest_data(db, request.cookies.get(get_settings().auth.guest_cookie), user.id)
    db.commit()
    logger.info("Registered user_id='%s'", user.id)
    _start_session(response, user, data.remember)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(data: LoginRequest, request: Request, response: Response, db: DbDep):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    claim_guest_data(db, request.cookies.get(get_settings().auth.guest_cookie), user.id)
    db.commit()
    _start_session(response, user, data.remember)
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(response: Response):
    clear_cookie(response, get_settings().auth.session_cookie)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
def me(user_id: UserIdDep, db: DbDep):
    return UserResponse.model_validate(db.get(User, user_id))


@router.get("/quota", response_model=GuestQuotaResponse)
def quota(owner: OwnerDep, db: DbDep):
    return GuestQuotaResponse(**get_quota(db, owner))


@router.patch("/me", response_model=UserResponse)
def update_profile(data: UpdateProfileRequest, user_id: UserIdDep, db: DbDep):
    user = db.get(User, user_id)
    assert user is not None  # require_user only returns ids of existing accounts
    user.name = data.name
    db.commit()
    return UserResponse.model_validate(user)


@router.post("/me/password")
def change_password(data: ChangePasswordRequest, user_id: UserIdDep, db: DbDep):
    user = _verified_user(db, user_id, data.current_password, "Password saat ini salah.")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"status": "updated"}


@router.delete("/me")
def delete_account(data: DeleteAccountRequest, response: Response, user_id: UserIdDep, db: DbDep):
    delete_user_account(db, _verified_user(db, user_id, data.password, "Password salah."))
    clear_cookie(response, get_settings().auth.session_cookie)
    return {"status": "deleted"}
