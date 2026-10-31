import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select

from app.api.deps import admin, database, roles
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.api.v1.auth import one_time
from app.core.errors import fail
from app.core.security import hash_password
from app.db.session import db_now
from app.models.articles import Article
from app.models.audit import AuditEvent
from app.models.notifications import OutboxEvent
from app.models.payments import PaymentAttempt
from app.models.reviews import Assignment
from app.models.taxonomy import SettingsVersion, Subject
from app.models.users import ReviewerProfile, User, UserRole
from app.repositories.articles import expected, locked_article
from app.repositories.assignments import LIVE, live_assignment
from app.schemas.admin import Extend, Policy, Reassign, UserUpdate
from app.schemas.payments import Publish, Verify, VerifyPublish
from app.schemas.reviews import Reason
from app.services import assignments, payments, publishing
from app.services.notifications import audit

router = APIRouter(prefix="/admin", route_class=IdempotentRoute)


@router.get("/users")
def users(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, User, select(User), limit, cursor, ("password_hash",))


@router.get("/reviewers")
def reviewers(user=Depends(admin), db=Depends(database)):
    return [record(p) for p in db.scalars(select(ReviewerProfile).limit(100))]


@router.get("/articles")
def articles(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, Article, select(Article), limit, cursor)


@router.post("/reviewers/{reviewer_id}/approve")
def approve(reviewer_id: UUID, data: Reason, user=Depends(admin), db=Depends(database)):
    target = db.get(User, reviewer_id)
    if not target or not target.active or not target.email_verified_at:
        fail("VERIFIED_USER_REQUIRED", 422)
    profile = db.get(ReviewerProfile, target.id)
    if not profile:
        profile = ReviewerProfile(user_id=target.id)
        db.add(profile)
    profile.approved, profile.approved_by = True, user.id
    if "REVIEWER" not in roles(db, target):
        db.add(UserRole(user_id=target.id, role="REVIEWER"))
    audit(db, user, "APPROVE_REVIEWER", target, {"reason": data.reason})
    return {"approved": True}


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, data: UserUpdate, user=Depends(admin), db=Depends(database)):
    db.execute(select(func.pg_advisory_xact_lock(17004)))
    # Serialize administrative role changes, including final-admin protection.
    db.execute(select(func.pg_advisory_xact_lock(17001)))
    target = db.get(User, user_id)
    if not target:
        fail("USER_NOT_FOUND", 404)
    live = db.scalars(
        select(Assignment)
        .where(Assignment.reviewer_id == user_id, Assignment.state.in_(LIVE))
        .order_by(Assignment.article_id)
    ).all()
    for a in live:
        article = locked_article(db, a.article_id)
        if not data.active or "REVIEWER" not in data.roles:
            assignments.revoke(db, article, a, user, data.reason)
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    if "ADMIN" in roles(db, target) and (not data.active or "ADMIN" not in data.roles):
        count = db.scalar(
            select(func.count())
            .select_from(User)
            .join(UserRole)
            .where(User.active, UserRole.role == "ADMIN")
        )
        if count <= 1:
            fail("FINAL_ADMIN_PROTECTED")
    target.active = data.active
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    db.add_all([UserRole(user_id=user_id, role=r) for r in set(data.roles)])
    audit(
        db,
        user,
        "UPDATE_USER",
        target,
        {"reason": data.reason, "active": data.active, "roles": data.roles},
    )
    return record(target, ("password_hash",))


@router.post("/articles/{article_id}/reassign")
def reassign(article_id: UUID, data: Reassign, user=Depends(admin), db=Depends(database)):
    article = locked_article(db, article_id)
    expected(article, data.expected_version)
    if article.status not in ("SUBMITTED", "IN_REVIEW"):
        fail("INVALID_TRANSITION")
    current = live_assignment(db, article_id)
    if current:
        assignments.revoke(db, article, current, user, data.reason)
    if data.reviewer_id:
        target = db.scalar(select(User).where(User.id == data.reviewer_id).with_for_update())
        if not assignments.eligible(db, target, article) or not assignments.capacity(db, target):
            fail("REVIEWER_INELIGIBLE", 422)
        return record(assignments.new_assignment(db, article, target, db_now(db)))
    return record(article)


@router.post("/assignments/{assignment_id}/extend")
def extend(assignment_id: UUID, data: Extend, user=Depends(admin), db=Depends(database)):
    hint = db.get(Assignment, assignment_id)
    if not hint:
        fail("ASSIGNMENT_NOT_FOUND", 404)
    article = locked_article(db, hint.article_id)
    a = db.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = db_now(db)
    if assignments.expire(db, article, a, now):
        db.commit()
        fail("ASSIGNMENT_EXPIRED")
    if a.state not in LIVE or data.new_due_at <= a.due_at:
        fail("INVALID_EXTENSION")
    a.due_at = data.new_due_at
    audit(
        db,
        user,
        "EXTEND_ASSIGNMENT",
        a,
        {"reason": data.reason, "due_at": data.new_due_at.isoformat()},
    )
    from app.services.notifications import emit

    emit(
        db,
        article.id,
        "DEADLINE_EXTENDED",
        [a.reviewer_id],
        f"extend:{a.id}:{data.new_due_at.isoformat()}",
    )
    return record(a)


@router.get("/payments")
def payment_list(user=Depends(admin), db=Depends(database)):
    return [
        record(p)
        for p in db.scalars(
            select(PaymentAttempt).where(PaymentAttempt.status == "SUBMITTED").limit(100)
        )
    ]


@router.post("/payment-attempts/{attempt_id}/verify")
def verify(attempt_id: UUID, data: Verify, user=Depends(admin), db=Depends(database)):
    return record(payments.verify(db, attempt_id, user, data))


@router.post("/payment-attempts/{attempt_id}/reject")
def reject(attempt_id: UUID, data: Reason, user=Depends(admin), db=Depends(database)):
    return record(payments.reject(db, attempt_id, user, data.reason))


@router.post("/articles/{article_id}/publish", status_code=201)
def publish(article_id: UUID, data: Publish, user=Depends(admin), db=Depends(database)):
    db.flush()
    item = publishing.publish(db, article_id, user, data)
    db.flush()
    return record(item)


@router.post("/articles/{article_id}/verify-and-publish", status_code=201)
def verify_publish(
    article_id: UUID, data: VerifyPublish, user=Depends(admin), db=Depends(database)
):
    # Lock requested article first, then validate payment belongs to it before mutation.
    article = locked_article(db, article_id)
    hint = db.get(PaymentAttempt, data.payment_attempt_id)
    from app.models.payments import Invoice

    if not hint or db.get(Invoice, hint.invoice_id).article_id != article.id:
        fail("PAYMENT_ARTICLE_MISMATCH", 422)
    payments.verify(db, hint.id, user, data.verification)
    item = publishing.publish(db, article.id, user, data)
    db.flush()
    return record(item)


@router.get("/settings")
def settings(user=Depends(admin), db=Depends(database)):
    version, values = assignments.policy(db)
    return {"version": version, "values": values}


@router.post("/settings", status_code=201)
def change_settings(data: Policy, user=Depends(admin), db=Depends(database)):
    db.execute(select(func.pg_advisory_xact_lock(17002)))
    version, _ = assignments.policy(db)
    item = SettingsVersion(version=version + 1, values=data.model_dump(), changed_by=user.id)
    db.add(item)
    db.flush()
    audit(db, user, "SETTINGS_CHANGED", item)
    return record(item)


@router.get("/audit")
def audits(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    return page(db, AuditEvent, select(AuditEvent), limit, cursor)


@router.get("/outbox")
def outbox(user=Depends(admin), db=Depends(database)):
    return [
        record(e, ("payload",))
        for e in db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.state != "SENT")
            .order_by(OutboxEvent.created_at)
            .limit(100)
        )
    ]


class Invitation(BaseModel):
    email: EmailStr
    subject_ids: list[UUID] = Field(min_length=1, max_length=100)


@router.post("/reviewer-invitations", status_code=201)
def invite(data: Invitation, user=Depends(admin), db=Depends(database)):
    targets = set(data.subject_ids)
    if len(
        list(db.scalars(select(Subject.id).where(Subject.id.in_(targets), Subject.active)))
    ) != len(targets):
        fail("INVALID_SUBJECTS", 422)
    target = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not target:
        target = User(
            email=str(data.email).lower(),
            display_name="Invited reviewer",
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(target)
        db.flush()
    if not target.active:
        fail("ACCOUNT_DISABLED", 422)
    profile = db.get(ReviewerProfile, target.id)
    if not profile:
        profile = ReviewerProfile(user_id=target.id)
        db.add(profile)
    profile.approved, profile.approved_by = True, user.id
    one_time(db, target, "REVIEWER_INVITE", {"subject_ids": [str(s) for s in targets]})
    audit(db, user, "INVITE_REVIEWER", target)
    return {"invited": True}
