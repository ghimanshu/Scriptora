from sqlalchemy import func, select

from app.db.session import db_now, session_factory
from app.models.reviews import Assignment
from app.repositories.articles import locked_article
from app.repositories.assignments import LIVE, live_assignment
from app.services.assignments import expire


def run():
    factory = session_factory()
    with factory() as db:
        ids = list(
            db.scalars(
                select(Assignment.article_id)
                .where(Assignment.state.in_(LIVE), Assignment.due_at <= func.clock_timestamp())
                .order_by(Assignment.due_at)
                .limit(100)
            )
        )
    for article_id in ids:
        with factory.begin() as db:
            article = locked_article(db, article_id, skip_locked=True)
            if article:
                expire(db, article, live_assignment(db, article_id), db_now(db))
