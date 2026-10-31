from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select

from app.api.deps import current_user, database
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.core.errors import fail
from app.models.articles import Article, ArticleVersion
from app.models.reviews import Assignment, Review, ReviewComment, StatusHistory
from app.repositories.articles import locked_article
from app.schemas.articles import Draft, Expected, Resubmit, VersionInput
from app.services import workflow

router = APIRouter(route_class=IdempotentRoute)


@router.get("/articles")
def list_articles(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(current_user),
    db=Depends(database),
):
    return page(db, Article, select(Article).where(Article.author_id == user.id), limit, cursor)


@router.post("/articles", status_code=201)
def create(data: Draft, user=Depends(current_user), db=Depends(database)):
    return record(workflow.create_draft(db, user, data))


@router.get("/articles/{article_id}")
def detail(article_id: UUID, user=Depends(current_user), db=Depends(database)):
    article = db.get(Article, article_id)
    if not article:
        fail("ARTICLE_NOT_FOUND", 404)
    workflow.can_read(db, article, user)
    result = record(article)
    result["current_version"] = record(db.get(ArticleVersion, article.current_version_id))
    reviews = db.scalars(
        select(Review)
        .join(Assignment, Review.assignment_id == Assignment.id)
        .where(Assignment.article_id == article_id, Review.submitted_at.is_not(None))
    ).all()
    result["reviews"] = [
        {
            **record(r),
            "numbered_comments": [
                record(c)
                for c in db.scalars(
                    select(ReviewComment).where(ReviewComment.review_id == r.id)
                ).all()
            ],
        }
        for r in reviews
    ]
    return result


def match_version(version, if_match):
    try:
        expected = int((if_match or "").strip('"'))
    except ValueError:
        fail("IF_MATCH_REQUIRED", 428)
    if version.lock_version != expected:
        fail("VERSION_CONFLICT")


@router.patch("/articles/{article_id}")
def edit(
    article_id: UUID,
    data: VersionInput,
    if_match: str | None = Header(None),
    user=Depends(current_user),
    db=Depends(database),
):
    article = locked_article(db, article_id)
    workflow.owner(article, user)
    match_version(article, if_match)
    if article.status != "DRAFT":
        fail("DRAFT_REQUIRED")
    version = db.get(ArticleVersion, article.current_version_id)
    version.data, version.manuscript_file_id = (
        data.metadata.model_dump(mode="json"),
        data.manuscript_file_id,
    )
    version.lock_version += 1
    article.lock_version += 1
    return record(article)


@router.post("/articles/{article_id}/submit")
def submit(article_id: UUID, data: Expected, user=Depends(current_user), db=Depends(database)):
    return record(workflow.submit(db, article_id, user, data))


@router.post("/articles/{article_id}/resubmit")
def resubmit(article_id: UUID, data: Resubmit, user=Depends(current_user), db=Depends(database)):
    return record(workflow.submit(db, article_id, user, data, revision=True))


@router.get("/articles/{article_id}/versions")
def versions(article_id: UUID, user=Depends(current_user), db=Depends(database)):
    article = db.get(Article, article_id)
    if not article:
        fail("ARTICLE_NOT_FOUND", 404)
    workflow.can_read(db, article, user)
    query = select(ArticleVersion).where(ArticleVersion.article_id == article_id)
    if user.id != article.author_id:
        query = query.where(ArticleVersion.submitted_at.is_not(None))
    return [record(v) for v in db.scalars(query.order_by(ArticleVersion.version_number)).all()]


@router.post("/articles/{article_id}/versions", status_code=201)
def new_version(
    article_id: UUID, data: VersionInput, user=Depends(current_user), db=Depends(database)
):
    return record(workflow.create_version(db, locked_article(db, article_id), user, data))


@router.patch("/articles/{article_id}/versions/{version_id}")
def edit_version(
    article_id: UUID,
    version_id: UUID,
    data: VersionInput,
    if_match: str | None = Header(None),
    user=Depends(current_user),
    db=Depends(database),
):
    article = locked_article(db, article_id)
    workflow.owner(article, user)
    version = db.get(ArticleVersion, version_id)
    if not version or version.article_id != article.id:
        fail("VERSION_NOT_FOUND", 404)
    match_version(version, if_match)
    if version.submitted_at or article.status not in ("DRAFT", "REVIEWED"):
        fail("IMMUTABLE_VERSION")
    version.data, version.manuscript_file_id = (
        data.metadata.model_dump(mode="json"),
        data.manuscript_file_id,
    )
    version.lock_version += 1
    return record(version)


@router.get("/articles/{article_id}/timeline")
def timeline(article_id: UUID, user=Depends(current_user), db=Depends(database)):
    article = db.get(Article, article_id)
    if not article:
        fail("ARTICLE_NOT_FOUND", 404)
    workflow.can_read(db, article, user)
    return [
        record(h)
        for h in db.scalars(
            select(StatusHistory)
            .where(StatusHistory.article_id == article.id)
            .order_by(StatusHistory.created_at)
        ).all()
    ]
