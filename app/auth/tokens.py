"""Login tokens (JWT access tokens) and the "who is calling?" dependency.

After a successful ``POST /users/login`` the client receives a signed token
and sends it back on later requests as ``Authorization: Bearer <token>``.
The token holds the user's id (``sub``) and an expiry time (``exp``); the
signature means the server can trust both without storing any session.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

# auto_error=False so a missing header gives our own 401 (with the
# WWW-Authenticate header) instead of FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)


class InvalidTokenError(Exception):
    """Raised when a token is malformed, badly signed or expired."""


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    """Return a signed JWT that identifies ``user_id`` until it expires."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    """Check the token's signature and expiry and return the user id inside it."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            # Pin the algorithm: never let the token choose it (e.g. "none").
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: the logged-in user, or 401 if the token is missing or bad."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized(str(exc)) from exc
    user = db.get(User, user_id)
    if user is None:
        # The token is valid but the account has since been deleted.
        raise _unauthorized("User no longer exists")
    return user
