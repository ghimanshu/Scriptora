import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import fail
from app.db.session import db_now, session_factory
from app.models.users import AuthSession, User, UserRole

bearer = HTTPBearer(auto_error=False)


def database(request: Request):
    shared = getattr(request.state, "command_db", None)
    if shared is not None:
        yield shared
        return
    with session_factory()() as db:
        db.info["request_id"] = getattr(request.state, "request_id", None)
        try:
            yield db
            db.commit()
        except IntegrityError:
            db.rollback()
            fail("CONFLICTING_WRITE", 409)
        except Exception:
            db.rollback()
            raise


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(database)
):
    if not credentials:
        fail("AUTHENTICATION_REQUIRED", 401)
    cfg = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            cfg.jwt_signing_key,
            algorithms=[cfg.jwt_algorithm],
            issuer=cfg.jwt_issuer,
            audience=cfg.jwt_audience,
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        user = db.get(User, uuid.UUID(claims["sub"]))
        session = db.get(AuthSession, uuid.UUID(claims["sid"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        fail("INVALID_TOKEN", 401)
    if (
        not user
        or not user.active
        or not user.email_verified_at
        or not session
        or session.user_id != user.id
        or session.revoked_at
        or session.expires_at <= db_now(db)
    ):
        fail("INVALID_SESSION", 401)
    return user


def roles(db, user):
    return set(db.scalars(select(UserRole.role).where(UserRole.user_id == user.id)))


def require_role(db, user, role):
    if role not in roles(db, user):
        fail("FORBIDDEN", 403)


def admin(user=Depends(current_user), db=Depends(database)):
    require_role(db, user, "ADMIN")
    return user
