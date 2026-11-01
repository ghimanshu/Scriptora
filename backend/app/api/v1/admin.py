import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import String, cast, delete, func, or_, select

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
from app.models.payments import Invoice, PaymentAttempt
from app.models.reviews import Assignment
from app.models.taxonomy import SettingsVersion, Subject
from app.models.users import ReviewerProfile, User, UserRole
from app.repositories.articles import expected, locked_article
from app.repositories.assignments import LIVE, live_assignment
from app.schemas.admin import DeleteArticle, Extend, Policy, Reassign, UserUpdate
from app.schemas.payments import Publish, Verify, VerifyPublish
from app.schemas.reviews import Reason
from app.services import assignments, payments, publishing
from app.services.notifications import audit, emit

router = APIRouter(prefix="/admin", route_class=IdempotentRoute)


@router.get("/users")
def users(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    result = page(db, User, select(User), limit, cursor, ("password_hash",))
    for item in result["items"]:
        item["name"] = item["display_name"]
        item["roles"] = sorted(roles(db, db.get(User, UUID(item["id"]))))
    return result


@router.get("/reviewers")
def reviewers(user=Depends(admin), db=Depends(database)):
    rows = db.execute(
        select(User, ReviewerProfile)
        .join(ReviewerProfile, ReviewerProfile.user_id == User.id)
        .where(ReviewerProfile.approved.is_(False), ReviewerProfile.rejected.is_(False))
        .order_by(User.created_at, User.id)
        .limit(100)
    )
    return {
        "items": [
            {
                "id": str(target.id),
                "name": target.display_name,
                "email": target.email,
                "email_verified": target.email_verified_at is not None,
                "active": target.active,
            }
            for target, profile in rows
        ],
        "next_cursor": None,
    }


@router.get("/articles")
def articles(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(admin),
    db=Depends(database),
):
    result = page(
        db,
        Article,
        select(Article).where(Article.status.not_in(("DRAFT", "DELETED"))),
        limit,
        cursor,
    )
    from app.models.articles import ArticleVersion

    for item in result["items"]:
        version = db.get(ArticleVersion, UUID(item["current_version_id"]))
        item["title"] = version.data.get("title", "")
        item["current_version_number"] = version.version_number
    return result


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: UUID, data: DeleteArticle, user=Depends(admin), db=Depends(database)
):
    from app.services.article_deletion import remove

    return remove(db, article_id, user, data.reason)


@router.post("/reviewers/{reviewer_id}/approve")
def approve(reviewer_id: UUID, data: Reason, user=Depends(admin), db=Depends(database)):
    return decide_reviewer(db, reviewer_id, data, user, approve=True)


@router.post("/reviewers/{reviewer_id}/reject")
def reject_reviewer(reviewer_id: UUID, data: Reason, user=Depends(admin), db=Depends(database)):
    return decide_reviewer(db, reviewer_id, data, user, approve=False)


def decide_reviewer(db, reviewer_id, data, actor, approve):
    target = db.scalar(select(User).where(User.id == reviewer_id).with_for_update())
    if not target or not target.active:
        fail("ACTIVE_USER_REQUIRED", 422)
    profile = db.scalar(
        select(ReviewerProfile).where(ReviewerProfile.user_id == reviewer_id).with_for_update()
    )
    if not profile:
        fail("REVIEWER_APPLICATION_NOT_FOUND", 404)
    if profile.approved or profile.rejected:
        fail("REVIEWER_APPLICATION_ALREADY_DECIDED", 409)
    profile.approved, profile.rejected = approve, not approve
    if approve:
        profile.approved_by = actor.id
        if "REVIEWER" not in roles(db, target):
            db.add(UserRole(user_id=target.id, role="REVIEWER"))
    kind = "REVIEWER_APPROVED" if approve else "REVIEWER_REJECTED"
    extra = {
        "title": "Reviewer application approved" if approve else "Reviewer application rejected",
        "message": "Your reviewer application has been "
        + ("approved." if approve else "rejected."),
        "reason": data.reason,
        "path": "/login",
    }
    if approve and not target.email_verified_at:
        one_time(db, target, "VERIFY_EMAIL", event_kind=kind, extra=extra)
    else:
        emit(db, target.id, kind, [target.id], f"reviewer-decision:{target.id}", extra)
    audit(
        db,
        actor,
        "APPROVE_REVIEWER" if approve else "REJECT_REVIEWER",
        target,
        {"reason": data.reason},
    )
    return {"approved": approve, "rejected": not approve}


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


@router.get("/articles/{article_id}/reviewers")
def eligible_reviewers(article_id: UUID, user=Depends(admin), db=Depends(database)):
    article = locked_article(db, article_id)
    if article.status != "SUBMITTED" or live_assignment(db, article.id):
        fail("ARTICLE_NOT_AVAILABLE_FOR_ASSIGNMENT")
    candidates = db.scalars(
        select(User)
        .join(ReviewerProfile, ReviewerProfile.user_id == User.id)
        .where(ReviewerProfile.approved.is_(True))
        .order_by(User.display_name, User.id)
    ).all()
    return {
        "items": [
            {"id": str(target.id), "name": target.display_name, "email": target.email}
            for target in candidates
            if assignments.eligible(db, target, article) and assignments.capacity(db, target)
        ]
    }


@router.post("/articles/{article_id}/assign")
@router.post("/articles/{article_id}/reassign")
def reassign(article_id: UUID, data: Reassign, user=Depends(admin), db=Depends(database)):
    db.execute(select(func.pg_advisory_xact_lock_shared(17004)))
    article = locked_article(db, article_id)
    expected(article, data.expected_version)
    if live_assignment(db, article_id):
        fail("ARTICLE_ALREADY_ASSIGNED")
    if article.status != "SUBMITTED":
        fail("INVALID_TRANSITION")
    if not data.reviewer_id:
        fail("REVIEWER_REQUIRED", 422)
    target = db.scalar(select(User).where(User.id == data.reviewer_id).with_for_update())
    if not assignments.eligible(db, target, article) or not assignments.capacity(db, target):
        fail("REVIEWER_INELIGIBLE", 422)
    assignment = assignments.new_assignment(db, article, target, db_now(db))
    audit(
        db,
        user,
        "ADMIN_ASSIGNED_REVIEWER",
        article,
        {"reviewer_id": str(target.id), "reason": data.reason},
    )
    return record(assignment)


@router.post("/assignments/{assignment_id}/extend")
def extend(assignment_id: UUID, data: Extend, user=Depends(admin), db=Depends(database)):
    fail("FIXED_REVIEW_DEADLINE", 409)


@router.get("/payments")
def payment_list(user=Depends(admin), db=Depends(database)):
    rows = db.execute(
        select(PaymentAttempt, Invoice)
        .join(Invoice, Invoice.id == PaymentAttempt.invoice_id)
        .join(Article, Article.id == Invoice.article_id)
        .where(PaymentAttempt.status == "SUBMITTED", Article.status == "PAID")
        .order_by(PaymentAttempt.created_at)
        .limit(100)
    )
    return [
        {
            **record(attempt),
            "article_id": str(invoice.article_id),
            "currency": invoice.currency,
            "reference": attempt.reference_normalized,
            "reason": attempt.rejection_reason,
        }
        for attempt, invoice in rows
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


@router.get("/audit-events")
def audit_events(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    search: str = Query("", max_length=200),
    user=Depends(admin),
    db=Depends(database),
):
    query = select(AuditEvent)
    term = search.strip()
    if term:
        query = query.where(
            or_(
                AuditEvent.action.icontains(term, autoescape=True),
                AuditEvent.entity_type.icontains(term, autoescape=True),
                cast(AuditEvent.entity_id, String).icontains(term, autoescape=True),
                AuditEvent.request_id.icontains(term, autoescape=True),
                AuditEvent.actor_id.in_(
                    select(User.id).where(User.display_name.icontains(term, autoescape=True))
                ),
            )
        )
    result = page(db, AuditEvent, query, limit, cursor, ("data",))
    actor_ids = {UUID(item["actor_id"]) for item in result["items"] if item["actor_id"]}
    actors = (
        {
            str(actor.id): actor.display_name
            for actor in db.scalars(select(User).where(User.id.in_(actor_ids)))
        }
        if actor_ids
        else {}
    )
    for item in result["items"]:
        item["event_type"] = item["action"]
        item["actor_name"] = actors.get(item["actor_id"])
        item["summary"] = f"{item['action']}: {item['entity_type']} {item['entity_id']}"
    return result


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
