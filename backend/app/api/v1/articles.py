from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select

from app.api.deps import current_user, database, roles
from app.api.idempotency import IdempotentRoute
from app.api.pagination import page
from app.api.serialization import record
from app.core.errors import fail
from app.models.articles import Article, ArticleVersion
from app.models.reviews import Assignment, Review, ReviewComment, StatusHistory
from app.models.taxonomy import Outlet, Subject
from app.repositories.articles import locked_article
from app.repositories.assignments import live_assignment
from app.schemas.articles import Draft, DraftUpdate, Expected, Resubmit, VersionInput
from app.services import workflow

router = APIRouter(route_class=IdempotentRoute)


@router.get("/articles")
def list_articles(
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(current_user),
    db=Depends(database),
):
    result = page(
        db,
        Article,
        select(Article).where(Article.author_id == user.id, Article.status != "DELETED"),
        limit,
        cursor,
    )
    version_ids = [
        UUID(item["current_version_id"]) for item in result["items"] if item["current_version_id"]
    ]
    versions = db.scalars(select(ArticleVersion).where(ArticleVersion.id.in_(version_ids))).all()
    titles = {str(version.id): version.data.get("title", "") for version in versions}
    for item in result["items"]:
        item["title"] = titles.get(item["current_version_id"], "")
        outlet = db.get(Outlet, UUID(item["outlet_id"]))
        subject = (
            db.get(Subject, UUID(item["primary_subject_id"]))
            if item["primary_subject_id"]
            else None
        )
        item["publication_type_id"] = str(outlet.type_id)
        item["outlet"] = outlet.name
        item["subject"] = subject.name if subject else None
    return result


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
    outlet = db.get(Outlet, article.outlet_id)
    subject = db.get(Subject, article.primary_subject_id) if article.primary_subject_id else None
    result["publication_type_id"] = str(outlet.type_id)
    result["outlet"] = outlet.name
    result["subject"] = subject.name if subject else None
    current = db.get(ArticleVersion, article.current_version_id)
    result["current_version"] = record(current)
    result["title"] = current.data.get("title", "")
    result["abstract"] = current.data.get("abstract", "")
    result["current_version_number"] = current.version_number
    result["allowed_actions"] = author_actions(article, user)
    assignment = live_assignment(db, article.id)
    result["assignment"] = record(assignment) if assignment else None
    if "ADMIN" in roles(db, user):
        if article.status == "SUBMITTED" and not assignment:
            result["allowed_actions"].append("ASSIGN")
        if article.status in ("APPROVED", "PAID", "PAYMENT_APPROVED", "PUBLISH"):
            result["allowed_actions"].append("VIEW_INVOICE")
        if article.status == "PAYMENT_APPROVED":
            result["allowed_actions"].append("PUBLISH")
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


def author_actions(article, user):
    if article.author_id != user.id:
        return []
    if article.status == "DRAFT":
        return ["EDIT", "SUBMIT"]
    if article.status == "REJECTED":
        return ["RESUBMIT"]
    if article.status in ("APPROVED", "PAID", "PAYMENT_APPROVED", "PUBLISH"):
        return ["VIEW_INVOICE"]
    return []


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
    data: DraftUpdate,
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
    if data.model_fields_set & {
        "primary_subject_id",
        "publication_type_id",
        "outlet_id",
        "template_id",
    }:
        workflow.update_draft_classification(db, article, version, data)
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
    items = []
    for version in db.scalars(query.order_by(ArticleVersion.version_number)).all():
        item = record(version)
        item["reviews"] = []
        for review in db.scalars(
            select(Review).where(Review.version_id == version.id, Review.submitted_at.is_not(None))
        ):
            item["reviews"].append(
                {
                    "id": str(review.id),
                    "decision": review.decision,
                    "summary": review.comments,
                    "comments": [
                        record(comment)
                        for comment in db.scalars(
                            select(ReviewComment)
                            .where(ReviewComment.review_id == review.id)
                            .order_by(ReviewComment.sequence)
                        )
                    ],
                }
            )
        items.append(item)
    return items


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
    if version.submitted_at or article.status not in ("DRAFT", "REJECTED"):
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
