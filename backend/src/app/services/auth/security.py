"""Password hashing and signed login tokens."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import bcrypt
import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_SECRET_FILE = Path("data/.jwt_secret")
_BCRYPT_MAX_BYTES = 72  # bcrypt hanya memakai 72 byte pertama


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except ValueError:
        return False


@lru_cache
def _jwt_secret() -> str:
    """JWT_SECRET dari .env; tanpa itu, rahasia acak disimpan di data/ agar login bertahan saat server restart."""
    configured = get_settings().auth.jwt_secret
    if configured:
        return configured
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_text(secret, encoding="utf-8")
    logger.warning("JWT_SECRET is not set; generated one at %s", _SECRET_FILE)
    return secret


def session_lifetime(remember: bool) -> timedelta:
    auth = get_settings().auth
    return timedelta(days=auth.remember_days if remember else auth.session_days)


def create_access_token(user_id: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + lifetime}, _jwt_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """User id dari token yang sah dan belum kedaluwarsa, selain itu None."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
