import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import fail
from app.db.session import db_now
from app.models.users import AuthSession

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        fail("PASSWORD_LENGTH_12_TO_128", 422)
    return hasher.hash(password)


def verify_password(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(db, user, family=None):
    cfg = get_settings()
    now = db_now(db)
    raw = secrets.token_urlsafe(48)
    session = AuthSession(
        user_id=user.id,
        token_family_id=family or uuid.uuid4(),
        refresh_token_hash=digest(raw),
        expires_at=now + timedelta(days=cfg.refresh_token_ttl_days),
    )
    db.add(session)
    db.flush()
    access = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(session.id),
            "iss": cfg.jwt_issuer,
            "aud": cfg.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=cfg.access_token_ttl_minutes),
        },
        cfg.jwt_signing_key,
        algorithm=cfg.jwt_algorithm,
    )
    return {
        "access_token": access,
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": cfg.access_token_ttl_minutes * 60,
    }
