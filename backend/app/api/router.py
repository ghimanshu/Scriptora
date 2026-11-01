from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text

from app.api.deps import current_user, database
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.api.v1 import admin, articles, auth, files, payments, public, reviewers, taxonomy
from app.core.errors import fail
from app.db.session import db_now
from app.models.notifications import Notification

router = APIRouter(route_class=IdempotentRoute)
for module in (auth, articles, reviewers, files, payments, admin, public, taxonomy):
    router.include_router(module.router)


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db=Depends(database)):
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "0009_draft_subjects":
            fail("SCHEMA_NOT_READY", 503)
        from app.core.config import get_settings
        from app.integrations.scanner import scan
        from app.integrations.storage import storage

        cfg = get_settings()
        if cfg.app_env == "production":
            scan(b"readiness probe")
            storage().client.head_bucket(Bucket=cfg.object_storage_bucket)
    except Exception:
        fail("DEPENDENCIES_NOT_READY", 503)
    return {"status": "ready", "schema": revision}


@router.get("/notifications")
def notifications(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(current_user),
    db=Depends(database),
):
    return page(
        db,
        Notification,
        select(Notification).where(Notification.recipient_id == user.id),
        limit,
        cursor,
    )


@router.post("/notifications/{notification_id}/read")
def read(notification_id: UUID, user=Depends(current_user), db=Depends(database)):
    item = db.get(Notification, notification_id)
    if not item or item.recipient_id != user.id:
        fail("NOTIFICATION_NOT_FOUND", 404)
    item.read_at = item.read_at or db_now(db)
    return record(item)
