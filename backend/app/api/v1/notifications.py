import base64
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, tuple_, update

from app.api.deps import current_user, database, roles
from app.api.idempotency import IdempotentRoute
from app.api.serialization import record
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import Article
from app.models.notifications import Notification
from app.schemas.notifications import (
    NotificationItem,
    NotificationPage,
    NotificationSummary,
    ReadAllResult,
)
from app.services.notifications import ARTICLE_EVENTS, notification_content

router = APIRouter(prefix="/notifications", route_class=IdempotentRoute)


def counts(db, user):
    total, unread = db.execute(
        select(func.count(), func.count().filter(Notification.read_at.is_(None))).where(
            Notification.recipient_id == user.id
        )
    ).one()
    return {"total_count": total, "unread_count": unread}


def notification_href(db, item, user, user_roles):
    payload = item.payload
    if item.type in ARTICLE_EVENTS:
        try:
            article = db.get(Article, UUID(payload.get("entity_id", "")))
        except (ValueError, TypeError, AttributeError):
            article = None
        if article:
            if user.id == article.author_id:
                return (
                    "/author/articles"
                    if article.status == "DELETED"
                    else f"/author/articles/{article.id}"
                )
            if "ADMIN" in user_roles:
                return (
                    "/admin/articles"
                    if article.status == "DELETED"
                    else f"/admin/articles/{article.id}"
                )
            if "REVIEWER" in user_roles:
                assignment_id = payload.get("assignment_id")
                if item.type in ("ASSIGNED", "DEADLINE_REMINDER") and assignment_id:
                    try:
                        return f"/reviewer/assignments/{UUID(assignment_id)}"
                    except (ValueError, TypeError):
                        pass
                return "/reviewer/queue" if item.type == "AVAILABLE" else "/reviewer/assignments"
    path = payload.get("path")
    if (
        isinstance(path, str)
        and ".." not in path
        and any(path.startswith(f"/{role.lower()}/") for role in user_roles)
    ):
        return path
    if (
        item.type in ("REVIEWER_APPLICATION", "REVISION_REVIEWER_UNAVAILABLE")
        and "ADMIN" in user_roles
    ):
        return "/admin/users" if item.type == "REVIEWER_APPLICATION" else "/admin/articles"
    return None


def serialize(db, item, user, user_roles):
    result = record(item)
    result["payload"] = {
        key: value
        for key, value in item.payload.items()
        if key not in ("encrypted_token", "recipients")
    }
    result.update(notification_content(item.type, result["payload"]))
    result["is_read"] = item.read_at is not None
    result["href"] = notification_href(db, item, user, user_roles)
    return result


@router.get("/summary", response_model=NotificationSummary)
def summary(user=Depends(current_user), db=Depends(database)):
    recent = db.scalars(
        select(Notification)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(5)
    )
    user_roles = roles(db, user)
    return {**counts(db, user), "items": [serialize(db, item, user, user_roles) for item in recent]}


@router.get("", response_model=NotificationPage)
def notifications(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    status: Literal["all", "read", "unread"] = "all",
    user=Depends(current_user),
    db=Depends(database),
):
    query = select(Notification).where(Notification.recipient_id == user.id)
    if status != "all":
        query = query.where(
            Notification.read_at.is_(None)
            if status == "unread"
            else Notification.read_at.is_not(None)
        )
    if cursor:
        try:
            stamp, key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            stamp = datetime.fromisoformat(stamp)
            if stamp.tzinfo is None:
                raise ValueError("Timezone required")
            query = query.where(
                tuple_(Notification.created_at, Notification.id) < tuple_(stamp, UUID(key))
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            fail("INVALID_CURSOR", 422)
    rows = list(
        db.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        base64.urlsafe_b64encode(
            json.dumps([rows[-1].created_at.isoformat(), str(rows[-1].id)]).encode()
        ).decode()
        if more
        else None
    )
    user_roles = roles(db, user)
    return {
        **counts(db, user),
        "items": [serialize(db, item, user, user_roles) for item in rows],
        "next_cursor": next_cursor,
    }


@router.post("/read-all", response_model=ReadAllResult)
def read_all(user=Depends(current_user), db=Depends(database)):
    now = db_now(db)
    result = db.execute(
        update(Notification)
        .where(
            Notification.recipient_id == user.id,
            Notification.read_at.is_(None),
            Notification.created_at <= now,
        )
        .values(read_at=now)
    )
    return {"updated_count": result.rowcount, "unread_count": counts(db, user)["unread_count"]}


def mark(notification_id, db, user, is_read):
    item = db.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.recipient_id == user.id)
        .with_for_update()
    )
    if not item:
        fail("NOTIFICATION_NOT_FOUND", 404)
    item.read_at = (item.read_at or db_now(db)) if is_read else None
    db.flush()
    return serialize(db, item, user, roles(db, user))


@router.post("/{notification_id}/read", response_model=NotificationItem)
def read(notification_id: UUID, user=Depends(current_user), db=Depends(database)):
    return mark(notification_id, db, user, True)


@router.post("/{notification_id}/unread", response_model=NotificationItem)
def unread(notification_id: UUID, user=Depends(current_user), db=Depends(database)):
    return mark(notification_id, db, user, False)
