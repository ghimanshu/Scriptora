"""Remove articles from use while retaining linked financial and audit records."""

from sqlalchemy import select, update

from app.db.session import db_now
from app.models.articles import ArticleVersion, File
from app.models.payments import Invoice
from app.models.reviews import Assignment, StatusHistory
from app.repositories.articles import locked_article
from app.repositories.assignments import LIVE
from app.services.notifications import audit, emit


def remove(db, article_id, actor, reason):
    article = locked_article(db, article_id)
    now = db_now(db)
    previous_status = article.status
    version = (
        db.get(ArticleVersion, article.current_version_id) if article.current_version_id else None
    )
    title = version.data.get("title", "Untitled article") if version else "Untitled article"
    for assignment in db.scalars(
        select(Assignment)
        .where(Assignment.article_id == article.id, Assignment.state.in_(LIVE))
        .with_for_update()
    ):
        assignment.state = "REVOKED"
        assignment.completed_at = now
        assignment.end_reason = reason
    for invoice in db.scalars(
        select(Invoice)
        .where(Invoice.article_id == article.id, Invoice.status == "OPEN")
        .with_for_update()
    ):
        invoice.status = "VOID"
    # Draft uploads may not have been bound to their article before submission.
    db.execute(
        update(File)
        .where(
            File.id.in_(
                select(ArticleVersion.manuscript_file_id).where(
                    ArticleVersion.article_id == article.id
                )
            ),
            File.article_id.is_(None),
            File.owner_user_id == article.author_id,
        )
        .values(article_id=article.id)
    )
    article.status = "DELETED"
    article.lock_version += 1
    article.pool_generation += 1
    db.add(
        StatusHistory(
            article_id=article.id,
            old_status=previous_status,
            new_status="DELETED",
            event_type="ARTICLE_DELETED",
            actor_id=actor.id,
            reason=reason,
        )
    )
    audit(
        db,
        actor,
        "ARTICLE_DELETED",
        article,
        {"reason": reason, "previous_status": previous_status},
    )
    emit(
        db,
        article.id,
        "ARTICLE_DELETED",
        [article.author_id],
        f"article-deleted:{article.id}",
        {
            "title": "Article deleted",
            "message": f"Your article {article.tracking_number} has been deleted by an administrator.",
            "article_title": title,
            "tracking_number": article.tracking_number,
            "reason": reason,
            "path": "/articles",
        },
    )
    return {"deleted": True, "article_id": str(article.id)}
