from sqlalchemy import select

from app.models.reviews import Assignment

LIVE = ("ACTIVE", "RESERVED")


def live_assignment(db, article_id):
    return db.scalar(
        select(Assignment)
        .where(Assignment.article_id == article_id, Assignment.state.in_(LIVE))
        .with_for_update()
    )
