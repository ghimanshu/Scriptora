from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import current_user, database, roles
from app.api.idempotency import IdempotentRoute
from app.api.serialization import record
from app.core.errors import fail
from app.models.articles import Article
from app.models.payments import Invoice, PaymentAttempt
from app.schemas.payments import PaymentInput
from app.services.payments import submit_payment

router = APIRouter(route_class=IdempotentRoute)


def access(db, invoice, user):
    if not invoice:
        fail("INVOICE_NOT_FOUND", 404)
    article = db.get(Article, invoice.article_id)
    if not article or article.status == "DELETED":
        fail("INVOICE_NOT_FOUND", 404)
    if article.author_id != user.id and "ADMIN" not in roles(db, user):
        fail("INVOICE_NOT_FOUND", 404)


@router.get("/articles/{article_id}/invoice")
def invoice(article_id: UUID, user=Depends(current_user), db=Depends(database)):
    item = db.scalar(select(Invoice).where(Invoice.article_id == article_id))
    access(db, item, user)
    return {**record(item), "payment_attempts": []}


@router.post("/invoices/{invoice_id}/payment-attempts", status_code=201)
def submit(invoice_id: UUID, data: PaymentInput, user=Depends(current_user), db=Depends(database)):
    return record(submit_payment(db, invoice_id, user, data))


@router.get("/invoices/{invoice_id}/payment-attempts")
def attempts(invoice_id: UUID, user=Depends(current_user), db=Depends(database)):
    access(db, db.get(Invoice, invoice_id), user)
    return [
        {**record(p), "reference": p.reference_normalized, "reason": p.rejection_reason}
        for p in db.scalars(
            select(PaymentAttempt).where(PaymentAttempt.invoice_id == invoice_id)
        ).all()
    ]
