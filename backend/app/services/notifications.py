import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import db_now
from app.models.articles import Article, ArticleVersion
from app.models.audit import AuditEvent
from app.models.notifications import Notification, OutboxEvent
from app.models.users import User, UserRole

ARTICLE_EVENTS = {
    "AVAILABLE",
    "NO_REVIEWER",
    "ARTICLE_SUBMITTED",
    "ARTICLE_RESUBMITTED",
    "ASSIGNED",
    "EXPIRED",
    "ASSIGNMENT_RELEASED",
    "ARTICLE_APPROVED",
    "ARTICLE_REJECTED",
    "PAYMENT_SUBMITTED",
    "PAYMENT_VERIFIED",
    "PAYMENT_REJECTED",
    "PUBLISHED",
    "ARTICLE_DELETED",
    "DEADLINE_REMINDER",
    "REVISION_REVIEWER_UNAVAILABLE",
}


def notification_content(kind, payload):
    labels = {
        "ARTICLE_SUBMITTED": (
            "Article submitted",
            "The article has been submitted and is awaiting a reviewer.",
        ),
        "ARTICLE_RESUBMITTED": (
            "Revision submitted",
            "The revised article has been submitted for review.",
        ),
        "AVAILABLE": (
            "Article available for review",
            "A manuscript in your subject is available in the review queue.",
        ),
        "NO_REVIEWER": ("Reviewer needed", "A submitted article needs an eligible reviewer."),
        "ASSIGNED": ("Reviewer assigned", "The article has been assigned for a five-day review."),
        "EXPIRED": ("Review deadline expired", "The article has returned to the review queue."),
        "ASSIGNMENT_RELEASED": (
            "Review assignment released",
            "The article is available for assignment again.",
        ),
        "ARTICLE_APPROVED": (
            "Article approved",
            "The article is approved. Payment is required before publication.",
        ),
        "ARTICLE_REJECTED": (
            "Changes requested",
            "Read the review feedback, revise the article, and resubmit it.",
        ),
        "PAYMENT_SUBMITTED": (
            "Payment proof submitted",
            "Payment proof is awaiting administrator verification.",
        ),
        "PAYMENT_VERIFIED": (
            "Payment approved",
            "The payment has been verified. The article is ready for publication.",
        ),
        "PAYMENT_REJECTED": (
            "Payment proof rejected",
            "Review the rejection reason and submit corrected payment proof.",
        ),
        "PUBLISHED": ("Article published", "The article is now available in the public library."),
        "DEADLINE_REMINDER": (
            "Review deadline reminder",
            "Your assigned review is approaching its deadline.",
        ),
        "VERIFY_EMAIL": (
            "Verify your email",
            "Use the verification link sent to your email address.",
        ),
        "RESET_PASSWORD": (
            "Password reset requested",
            "Password reset instructions have been sent to your email address.",
        ),
        "REVIEWER_INVITE": (
            "Reviewer invitation",
            "You have been invited to join as a reviewer. Check your email for instructions.",
        ),
        "DELIVERY_FAILED": (
            "Email delivery failed",
            "An email could not be delivered. Review the delivery service.",
        ),
    }
    title, message = labels.get(
        kind, (kind.replace("_", " ").title(), "An update is available in your workspace.")
    )
    return {"title": payload.get("title") or title, "message": payload.get("message") or message}


def admins(db):
    return list(db.scalars(select(UserRole.user_id).where(UserRole.role == "ADMIN")))


def emit(db, aggregate, kind, recipients, key, extra=None):
    recipients = list({uuid.UUID(str(value)) for value in recipients})
    payload = {"recipients": [str(value) for value in recipients], "entity_id": str(aggregate)}
    payload.update(extra or {})
    if kind in ARTICLE_EVENTS and not payload.get("article_title"):
        article = db.get(Article, aggregate)
        if article:
            version = (
                db.get(ArticleVersion, article.current_version_id)
                if article.current_version_id
                else None
            )
            payload["article_title"] = (
                version.data.get("title") if version else article.tracking_number
            )
    payload.update(notification_content(kind, payload))
    event_id = db.scalar(
        insert(OutboxEvent)
        .values(
            id=uuid.uuid4(),
            aggregate_id=aggregate,
            type=kind,
            payload=payload,
            dedupe_key=key,
            state="PENDING",
            attempt_count=0,
            available_at=db_now(db),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(OutboxEvent.id)
    )
    if event_id is None:
        return
    safe = {
        key: value for key, value in payload.items() if key not in ("encrypted_token", "recipients")
    }
    query = select(User.id).where(User.id.in_(recipients))
    if kind != "ARTICLE_DELETED":
        query = query.where(User.active.is_(True))
    for recipient_id in db.scalars(query):
        db.execute(
            insert(Notification)
            .values(
                id=uuid.uuid4(),
                recipient_id=recipient_id,
                event_id=event_id,
                type=kind,
                payload=safe,
            )
            .on_conflict_do_nothing(index_elements=["recipient_id", "event_id"])
        )


def audit(db, actor, action, entity, data=None):
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity.__tablename__,
            entity_id=entity.id,
            data=data or {},
            request_id=db.info.get("request_id"),
        )
    )
