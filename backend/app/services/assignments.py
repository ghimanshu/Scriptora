from datetime import timedelta

from sqlalchemy import func, or_, select

from app.api.deps import roles
from app.core.config import get_settings
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import VersionAuthor
from app.models.reviews import Assignment, StatusHistory
from app.models.taxonomy import SettingsVersion
from app.models.users import ReviewerConflict, ReviewerProfile, ReviewerSubject, User
from app.repositories.articles import expected, locked_article
from app.repositories.assignments import LIVE, live_assignment
from app.services.notifications import admins, audit, emit


def policy(db):
    cfg = get_settings()
    row = db.scalar(select(SettingsVersion).order_by(SettingsVersion.version.desc()).limit(1))
    return row.version if row else 0, row.values if row else {
        "review_duration_hours": cfg.default_review_duration_hours,
        "publication_fee_minor": cfg.default_publication_fee_minor,
        "max_live_assignments": cfg.default_max_live_assignments,
        "payment_instructions": "",
    }


def eligible(db, user, article, require_available=True):
    if (
        not user
        or not user.active
        or not user.email_verified_at
        or "REVIEWER" not in roles(db, user)
        or user.id == article.author_id
    ):
        return False
    profile = db.get(ReviewerProfile, user.id)
    if (
        not profile
        or not profile.approved
        or (require_available and not profile.available)
        or not db.get(ReviewerSubject, (user.id, article.primary_subject_id))
    ):
        return False
    conflict = db.scalar(
        select(ReviewerConflict.id)
        .where(
            ReviewerConflict.reviewer_id == user.id,
            or_(
                ReviewerConflict.article_id == article.id,
                ReviewerConflict.author_user_id == article.author_id,
            ),
        )
        .limit(1)
    )
    coauthor = db.scalar(
        select(VersionAuthor.id)
        .where(
            VersionAuthor.version_id == article.current_version_id,
            or_(VersionAuthor.user_id == user.id, func.lower(VersionAuthor.email) == user.email),
        )
        .limit(1)
    )
    return not conflict and not coauthor


def capacity(db, user):
    _, settings = policy(db)
    return (
        db.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(Assignment.reviewer_id == user.id, Assignment.state.in_(LIVE))
        )
        < settings["max_live_assignments"]
    )


def transition(db, article, state, event, actor=None, reason=""):
    db.add(
        StatusHistory(
            article_id=article.id,
            old_status=article.status,
            new_status=state,
            event_type=event,
            actor_id=actor.id if actor else None,
            reason=reason,
        )
    )
    article.status = state
    article.lock_version += 1
    audit(db, actor, event, article)


def pool(db, article):
    article.pool_generation += 1
    candidates = db.scalars(
        select(User)
        .join(ReviewerSubject, ReviewerSubject.reviewer_id == User.id)
        .where(ReviewerSubject.subject_id == article.primary_subject_id)
    ).all()
    targets = [u.id for u in candidates if eligible(db, u, article)]
    emit(
        db,
        article.id,
        "AVAILABLE" if targets else "NO_REVIEWER",
        targets or admins(db),
        f"pool:{article.id}:{article.pool_generation}",
        {"generation": article.pool_generation},
    )


def expire(db, article, assignment, now):
    if assignment and assignment.state in LIVE and now >= assignment.due_at:
        assignment.state = "EXPIRED"
        assignment.completed_at = now
        transition(db, article, "SUBMITTED", "EXPIRED")
        emit(
            db,
            article.id,
            "EXPIRED",
            [assignment.reviewer_id, article.author_id],
            f"expired:{assignment.id}",
        )
        db.flush()
        pool(db, article)
        return True
    return False


def new_assignment(db, article, user, now):
    duration = 120
    assignment = Assignment(
        article_id=article.id,
        round_id=article.current_round_id,
        version_id=article.current_version_id,
        reviewer_id=user.id,
        state="ACTIVE",
        assigned_at=now,
        started_at=now,
        due_at=now + timedelta(hours=duration),
        duration_hours=duration,
    )
    db.add(assignment)
    db.flush()
    transition(
        db,
        article,
        "ASSIGNED",
        "ASSIGNED",
        user,
    )
    emit(db, article.id, "ASSIGNED", [user.id, article.author_id], f"assigned:{assignment.id}")
    return assignment


def claim(db, article_id, user, version):
    db.execute(select(func.pg_advisory_xact_lock_shared(17004)))
    article = locked_article(db, article_id)
    db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assignment = live_assignment(db, article.id)
    now = db_now(db)
    expired = expire(db, article, assignment, now)
    if expired:
        db.commit()
        fail("ASSIGNMENT_EXPIRED_REFRESH")
    expected(article, version)
    if article.status != "SUBMITTED" or assignment:
        fail("ARTICLE_ALREADY_ASSIGNED")
    if not eligible(db, user, article):
        fail("REVIEWER_INELIGIBLE", 403)
    if not capacity(db, user):
        fail("REVIEWER_AT_CAPACITY")
    return new_assignment(db, article, user, now)


def lock_assignment(db, assignment_id, user, require_active=True):
    hint = db.get(Assignment, assignment_id)
    if not hint:
        fail("ASSIGNMENT_NOT_FOUND", 404)
    article = locked_article(db, hint.article_id)
    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = db_now(db)
    if assignment.reviewer_id != user.id:
        fail("FORBIDDEN", 403)
    if expire(db, article, assignment, now):
        db.commit()
        fail("ASSIGNMENT_EXPIRED")
    if (
        assignment.state not in LIVE
        or (require_active and assignment.state != "ACTIVE")
        or assignment.version_id != article.current_version_id
        or not eligible(db, user, article, require_available=False)
    ):
        fail("ASSIGNMENT_NOT_WRITABLE")
    return article, assignment, now


def revoke(db, article, assignment, actor, reason, state="REVOKED"):
    assignment.state = state
    assignment.completed_at = db_now(db)
    assignment.end_reason = reason
    transition(db, article, "SUBMITTED", state, actor, reason)
    db.flush()
    pool(db, article)
