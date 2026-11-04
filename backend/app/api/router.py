from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.deps import database
from app.api.idempotency import IdempotentRoute
from app.api.v1 import (
    admin,
    articles,
    auth,
    files,
    notifications,
    payments,
    public,
    reviewers,
    taxonomy,
)
from app.core.errors import fail

router = APIRouter(route_class=IdempotentRoute)
for module in (auth, articles, reviewers, files, payments, admin, public, taxonomy, notifications):
    router.include_router(module.router)


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db=Depends(database)):
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "0010_notification_inbox":
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
