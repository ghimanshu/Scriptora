from sqlalchemy import select

from app.models.payments import Invoice


def invoice_for_article(db, article_id):
    return db.scalar(select(Invoice).where(Invoice.article_id == article_id).with_for_update())
