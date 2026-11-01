import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import current_user, database
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.core.errors import fail
from app.integrations.storage import storage
from app.models.articles import Article, File
from app.models.payments import Publication
from app.models.taxonomy import Outlet, PublicationType, Subject, Template

router = APIRouter(route_class=IdempotentRoute)


@router.get("/subjects")
def subjects(db=Depends(database)):
    return [
        record(s) for s in db.scalars(select(Subject).where(Subject.active).order_by(Subject.name))
    ]


@router.get("/publication-types")
def types(db=Depends(database)):
    return [record(s) for s in db.scalars(select(PublicationType).where(PublicationType.active))]


@router.get("/outlets")
def outlets(db=Depends(database)):
    templates = db.scalars(
        select(Template).where(Template.active).order_by(Template.version.desc())
    ).all()
    latest: dict[UUID, str] = {}
    for item in templates:
        latest.setdefault(item.outlet_id, str(item.id))
    return [
        {**record(outlet), "template_id": latest.get(outlet.id)}
        for outlet in db.scalars(select(Outlet).where(Outlet.active))
    ]


@router.get("/templates/{template_id}")
def template(template_id: UUID, user=Depends(current_user), db=Depends(database)):
    item = db.get(Template, template_id)
    if not item:
        fail("TEMPLATE_NOT_FOUND", 404)
    return record(item)


@router.get("/public/articles")
def catalog(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    subject_id: UUID | None = None,
    outlet_id: UUID | None = None,
    db=Depends(database),
):
    query = (
        select(Publication)
        .join(Article, Article.id == Publication.article_id)
        .where(Article.status != "DELETED")
    )
    if subject_id:
        query = query.where(Publication.data["subject_id"].astext == str(subject_id))
    if outlet_id:
        query = query.where(Publication.data["outlet_id"].astext == str(outlet_id))
    return page(db, Publication, query, limit, cursor, ("published_by",))


@router.get("/public/articles/{slug}")
def article(slug: str, db=Depends(database)):
    item = db.scalar(
        select(Publication)
        .join(Article, Article.id == Publication.article_id)
        .where(Publication.slug == slug, Article.status != "DELETED")
    )
    if not item:
        fail("PUBLICATION_NOT_FOUND", 404)
    return record(item, ("published_by",))


@router.get("/public/articles/{slug}/download")
def download(slug: str, db=Depends(database)):
    item = db.scalar(
        select(Publication)
        .join(Article, Article.id == Publication.article_id)
        .where(Publication.slug == slug, Article.status != "DELETED")
    )
    if not item:
        fail("PUBLICATION_NOT_FOUND", 404)
    file = db.get(File, item.final_file_id)
    if file.scan_status != "CLEAN":
        fail("PUBLICATION_FILE_UNAVAILABLE", 503)
    return StreamingResponse(
        io.BytesIO(storage().get(file.storage_key)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{item.slug}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
