from sqlalchemy import select

from app.core.errors import fail
from app.models.articles import Article


def locked_article(db, article_id, skip_locked=False):
    item = db.scalar(
        select(Article).where(Article.id == article_id).with_for_update(skip_locked=skip_locked)
    )
    if not item and not skip_locked:
        fail("ARTICLE_NOT_FOUND", 404)
    return item


def expected(article, version):
    if article.lock_version != version:
        fail("VERSION_CONFLICT")
