from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select

from app.api.deps import current_user, database, require_role
from app.api.idempotency import IdempotentRoute
from app.api.serialization import record
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import Article, ArticleVersion
from app.models.reviews import Assignment
from app.models.taxonomy import Subject
from app.models.users import ReviewerConflict, ReviewerProfile, ReviewerSubject, User
from app.repositories.articles import locked_article
from app.repositories.assignments import LIVE, live_assignment
from app.schemas.admin import Availability, Subjects
from app.schemas.articles import Expected
from app.schemas.reviews import Feedback, Reason
from app.services import assignments, reviews

router = APIRouter(route_class=IdempotentRoute)


def reviewer(db, user):
    require_role(db, user, "REVIEWER")
    profile = db.get(ReviewerProfile, user.id)
    if not profile or not profile.approved:
        fail("REVIEWER_APPROVAL_REQUIRED", 403)
    return profile


@router.get("/reviewers/me/subjects")
def subjects(user=Depends(current_user), db=Depends(database)):
    reviewer(db, user)
    return list(
        db.scalars(select(ReviewerSubject.subject_id).where(ReviewerSubject.reviewer_id == user.id))
    )


@router.put("/reviewers/me/subjects")
def replace_subjects(data: Subjects, user=Depends(current_user), db=Depends(database)):
    db.execute(select(func.pg_advisory_xact_lock(17004)))
    reviewer(db, user)
    subject_ids = set(data.subject_ids)
    if len(
        list(db.scalars(select(Subject.id).where(Subject.id.in_(subject_ids), Subject.active)))
    ) != len(subject_ids):
        fail("INVALID_SUBJECT", 422)
    # Article locks precede reviewer lock, matching claims.
    live = db.scalars(
        select(Assignment)
        .where(Assignment.reviewer_id == user.id, Assignment.state.in_(LIVE))
        .order_by(Assignment.article_id)
    ).all()
    for a in live:
        article = locked_article(db, a.article_id)
        if article.primary_subject_id not in subject_ids:
            assignments.revoke(db, article, a, user, "Subject subscription removed")
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    db.execute(delete(ReviewerSubject).where(ReviewerSubject.reviewer_id == user.id))
    db.add_all([ReviewerSubject(reviewer_id=user.id, subject_id=s) for s in subject_ids])
    return {"subject_ids": list(subject_ids)}


@router.patch("/reviewers/me/availability")
def availability(data: Availability, user=Depends(current_user), db=Depends(database)):
    reviewer(db, user).available = data.available
    return data


@router.post("/articles/{article_id}/conflicts")
def conflict(article_id: UUID, data: Reason, user=Depends(current_user), db=Depends(database)):
    reviewer(db, user)
    article = locked_article(db, article_id)
    db.add(ReviewerConflict(reviewer_id=user.id, article_id=article.id, reason=data.reason))
    db.flush()
    a = live_assignment(db, article.id)
    if a and a.reviewer_id == user.id:
        assignments.revoke(db, article, a, user, data.reason, "RELEASED")
    return {"declared": True}


@router.get("/review-queue")
def queue(limit: int = Query(25, ge=1, le=100), user=Depends(current_user), db=Depends(database)):
    reviewer(db, user)
    live = select(Assignment.article_id).where(Assignment.state.in_(LIVE))
    rows = db.scalars(
        select(Article)
        .join(ReviewerSubject, ReviewerSubject.subject_id == Article.primary_subject_id)
        .where(
            ReviewerSubject.reviewer_id == user.id,
            Article.status == "SUBMITTED",
            Article.id.not_in(live),
        )
        .order_by(Article.submitted_at, Article.id)
        .limit(limit * 5)
    ).all()
    result = []
    for article in rows:
        if assignments.eligible(db, user, article):
            v = db.get(ArticleVersion, article.current_version_id)
            result.append(
                {
                    "id": str(article.id),
                    "title": v.data["title"],
                    "abstract": v.data.get("abstract"),
                    "subject_id": str(article.primary_subject_id),
                    "submitted_at": article.submitted_at,
                    "lock_version": article.lock_version,
                }
            )
        if len(result) == limit:
            break
    return {"items": result}


@router.get("/assignments/me")
def mine(user=Depends(current_user), db=Depends(database)):
    reviewer(db, user)
    now = db_now(db)
    return [
        {
            **record(a),
            "title": db.get(ArticleVersion, a.version_id).data.get("title", ""),
            "effective_assignment_state": "EXPIRED"
            if a.state in LIVE and a.due_at <= now
            else a.state,
        }
        for a in db.scalars(
            select(Assignment)
            .where(Assignment.reviewer_id == user.id)
            .order_by(Assignment.created_at.desc())
            .limit(100)
        )
    ]


@router.post("/articles/{article_id}/claim", status_code=201)
def claim(article_id: UUID, data: Expected, user=Depends(current_user), db=Depends(database)):
    return record(assignments.claim(db, article_id, user, data.expected_version))


@router.post("/assignments/{assignment_id}/start")
def start(assignment_id: UUID, user=Depends(current_user), db=Depends(database)):
    article, a, now = assignments.lock_assignment(db, assignment_id, user, False)
    if a.state != "RESERVED":
        fail("RESERVATION_REQUIRED")
    a.state, a.started_at = "ACTIVE", now
    assignments.transition(db, article, "ASSIGNED", "STARTED", user)
    return record(a)


@router.post("/assignments/{assignment_id}/release")
def release(assignment_id: UUID, data: Reason, user=Depends(current_user), db=Depends(database)):
    article, a, _ = assignments.lock_assignment(db, assignment_id, user, False)
    assignments.revoke(db, article, a, user, data.reason, "RELEASED")
    return record(a)


@router.put("/assignments/{assignment_id}/review-draft")
def draft(assignment_id: UUID, data: Feedback, user=Depends(current_user), db=Depends(database)):
    return record(reviews.save_review(db, assignment_id, user, data, False))


@router.post("/assignments/{assignment_id}/review")
def final(assignment_id: UUID, data: Feedback, user=Depends(current_user), db=Depends(database)):
    return record(reviews.save_review(db, assignment_id, user, data))
