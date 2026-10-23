"""Request dependencies: the database session and who is calling (account or guest browser)."""

import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.models.db_models import User
from app.services.auth.owner import Owner
from app.services.auth.security import decode_access_token

_GUEST_COOKIE_LIFETIME = timedelta(days=365)  # data tamu sendiri dihapus server setelah TTL tidak aktif


def get_db() -> Generator[Session, None, None]:
    with get_session() as db:
        yield db


# "function": closed when the endpoint returns, not held through background jobs or SSE streams
DbDep = Annotated[Session, Depends(get_db, scope="function")]


def set_cookie(response: Response, name: str, value: str, lifetime: timedelta) -> None:
    auth = get_settings().auth
    response.set_cookie(
        name,
        value,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=auth.cookie_secure,
        path="/",
    )


def clear_cookie(response: Response, name: str) -> None:
    auth = get_settings().auth
    response.delete_cookie(name, path="/", httponly=True, samesite="lax", secure=auth.cookie_secure)


def current_user_id(request: Request, db: Session) -> str | None:
    """User id dari cookie login yang sah dan akunnya masih ada."""
    token = request.cookies.get(get_settings().auth.session_cookie)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    exists = db.query(User.id).filter(User.id == user_id).first() is not None
    return user_id if exists else None


def get_owner(request: Request, response: Response, db: DbDep) -> Owner:
    """Akun yang login, atau tamu yang dikenali dari cookie browser (dibuat saat pertama kali)."""
    user_id = current_user_id(request, db)
    if user_id is not None:
        return Owner(user_id=user_id)
    guest_cookie = get_settings().auth.guest_cookie
    guest_id = request.cookies.get(guest_cookie)
    if not guest_id:
        guest_id = str(uuid.uuid4())
        set_cookie(response, guest_cookie, guest_id, _GUEST_COOKIE_LIFETIME)
    return Owner(guest_id=guest_id)


OwnerDep = Annotated[Owner, Depends(get_owner)]


def require_user(owner: OwnerDep) -> str:
    if owner.user_id is None:
        raise HTTPException(status_code=401, detail="Silakan masuk terlebih dahulu.")
    return owner.user_id


UserIdDep = Annotated[str, Depends(require_user)]
