import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import current_user, database, roles
from app.api.idempotency import IdempotentRoute
from app.core.errors import fail
from app.core.secrets import seal
from app.core.security import digest, hash_password, hasher, issue_session, verify_password
from app.db.session import db_now
from app.models.taxonomy import Subject
from app.models.users import (
    AuthSession,
    OneTimeToken,
    RateLimit,
    ReviewerProfile,
    ReviewerSubject,
    User,
    UserRole,
)
from app.schemas.auth import Forgot, InvitationAccept, Login, Refresh, Register, Reset, Token
from app.services.notifications import admins, emit

router = APIRouter(route_class=IdempotentRoute)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def throttle(db, key):
    now = db_now(db)
    db.execute(
        insert(RateLimit)
        .values(key=key, count=0, resets_at=now + timedelta(minutes=15))
        .on_conflict_do_nothing(index_elements=["key"])
    )
    row = db.scalar(select(RateLimit).where(RateLimit.key == key).with_for_update())
    if row.resets_at <= now:
        row.count, row.resets_at = 0, now + timedelta(minutes=15)
    row.count += 1
    blocked = row.count > 30
    db.commit()
    if blocked:
        fail("RATE_LIMITED", 429)


def one_time(db, user, purpose, context=None, event_kind=None, extra=None):
    raw = secrets.token_urlsafe(48)
    token = OneTimeToken(
        user_id=user.id,
        purpose=purpose,
        context=context or {},
        token_hash=digest(raw),
        expires_at=db_now(db) + timedelta(hours=1),
    )
    db.add(token)
    db.flush()
    emit(
        db,
        user.id,
        event_kind or purpose,
        [user.id],
        f"token:{token.id}",
        {**(extra or {}), "encrypted_token": seal(raw)},
    )


@router.post("/auth/register", status_code=201)
def register(data: Register, request: Request, db=Depends(database)):
    throttle(db, "register:" + (request.client.host if request.client else "unknown"))
    existing = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not existing:
        user = User(
            email=str(data.email).lower(),
            display_name=data.display_name,
            password_hash=hash_password(data.password),
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role=data.role))
        if data.role == "REVIEWER":
            db.add(ReviewerProfile(user_id=user.id, approved=False, rejected=False))
            emit(
                db,
                user.id,
                "REVIEWER_APPLICATION",
                admins(db),
                f"reviewer-application:{user.id}",
                {
                    "title": "Reviewer application awaiting review",
                    "message": f"{user.display_name} ({user.email}) applied to become a reviewer.",
                    "applicant_name": user.display_name,
                    "applicant_email": user.email,
                    "path": "/admin/users",
                },
            )
        else:
            one_time(db, user, "VERIFY_EMAIL")
    return {
        "message": "Application submitted for admin review"
        if data.role == "REVIEWER"
        else "Verification pending; check your email"
    }


def consume(db, raw, purpose):
    token = db.scalar(
        select(OneTimeToken).where(OneTimeToken.token_hash == digest(raw)).with_for_update()
    )
    if not token or token.purpose != purpose or token.used_at or token.expires_at <= db_now(db):
        fail("INVALID_OR_EXPIRED_TOKEN", 400)
    token.used_at = db_now(db)
    return db.get(User, token.user_id)


@router.post("/auth/verify-email", status_code=204)
def verify_email(data: Token, db=Depends(database)):
    user = consume(db, data.token, "VERIFY_EMAIL")
    user.email_verified_at = db_now(db)


def require_reviewer_approval(db, user):
    if roles(db, user) == {"REVIEWER"}:
        profile = db.get(ReviewerProfile, user.id)
        if profile and profile.rejected:
            fail("REVIEWER_APPLICATION_REJECTED", 403)
        if not profile or not profile.approved:
            fail("REVIEWER_APPROVAL_PENDING", 403)


@router.post("/auth/login")
def login(data: Login, request: Request, db=Depends(database)):
    throttle(db, "login:" + digest(str(data.email).lower()))
    throttle(db, "login-ip:" + (request.client.host if request.client else "unknown"))
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.active:
        fail("INVALID_CREDENTIALS", 401)
    require_reviewer_approval(db, user)
    if not user.email_verified_at:
        fail("EMAIL_VERIFICATION_REQUIRED", 403)
    return issue_session(db, user)


@router.post("/auth/refresh")
def refresh(data: Refresh, db=Depends(database)):
    hint = db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == digest(data.refresh_token))
    )
    if not hint:
        fail("INVALID_REFRESH_TOKEN", 401)
    # Lock the family root so refresh replay cannot race a new session insert.
    db.scalar(select(User).where(User.id == hint.user_id).with_for_update())
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.id == hint.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session.revoked_at:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_family_id == session.token_family_id)
            .values(revoked_at=db_now(db))
        )
        db.commit()
        fail("REFRESH_REPLAY", 401)
    user = db.get(User, session.user_id)
    if session.expires_at <= db_now(db) or not user.active or not user.email_verified_at:
        fail("INVALID_REFRESH_TOKEN", 401)
    require_reviewer_approval(db, user)
    session.revoked_at = db_now(db)
    return issue_session(db, user, session.token_family_id)


@router.post("/auth/logout", status_code=204)
def logout(user=Depends(current_user), db=Depends(database)):
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=db_now(db))
    )


@router.post("/auth/forgot-password", status_code=202)
def forgot(data: Forgot, db=Depends(database)):
    throttle(db, "forgot:" + digest(str(data.email).lower()))
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user and user.active:
        one_time(db, user, "RESET_PASSWORD")
    return {"message": "If eligible, a reset email will arrive"}


@router.post("/auth/reset-password", status_code=204)
def reset(data: Reset, db=Depends(database)):
    user = consume(db, data.token, "RESET_PASSWORD")
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    user.password_hash = hash_password(data.password)
    db.execute(
        update(AuthSession).where(AuthSession.user_id == user.id).values(revoked_at=db_now(db))
    )


@router.get("/me")
def me(user=Depends(current_user), db=Depends(database)):
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "roles": sorted(roles(db, user)),
    }


@router.post("/auth/accept-reviewer-invitation", status_code=204)
def accept_invitation(data: InvitationAccept, db=Depends(database)):
    token = db.scalar(
        select(OneTimeToken).where(OneTimeToken.token_hash == digest(data.token)).with_for_update()
    )
    user = consume(db, data.token, "REVIEWER_INVITE")
    user.password_hash = hash_password(data.password)
    user.display_name = data.display_name
    user.email_verified_at = db_now(db)
    if "REVIEWER" not in roles(db, user):
        db.add(UserRole(user_id=user.id, role="REVIEWER"))
    for raw in token.context.get("subject_ids", []):
        subject_id = uuid.UUID(raw)
        subject = db.get(Subject, subject_id)
        if subject and subject.active and not db.get(ReviewerSubject, (user.id, subject_id)):
            db.add(ReviewerSubject(reviewer_id=user.id, subject_id=subject_id))
    db.execute(
        update(AuthSession).where(AuthSession.user_id == user.id).values(revoked_at=db_now(db))
    )
