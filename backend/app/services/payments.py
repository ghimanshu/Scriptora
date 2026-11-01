from sqlalchemy import select

from app.api.deps import require_role
from app.core.errors import fail
from app.db.session import db_now
from app.models.payments import Invoice, PaymentAttempt
from app.repositories.articles import locked_article
from app.services.assignments import transition
from app.services.notifications import admins, audit, emit
from app.services.workflow import clean_file, owner


def normalize_reference(value):
    return "".join(value.upper().split()).replace("-", "")


def payment_locks(db, attempt_id):
    hint = db.get(PaymentAttempt, attempt_id)
    if not hint:
        fail("PAYMENT_NOT_FOUND", 404)
    invoice_hint = db.get(Invoice, hint.invoice_id)
    article = locked_article(db, invoice_hint.article_id)
    invoice = db.scalar(select(Invoice).where(Invoice.id == hint.invoice_id).with_for_update())
    attempt = db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == attempt_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return article, invoice, attempt


def submit_payment(db, invoice_id, user, data):
    hint = db.get(Invoice, invoice_id)
    if not hint:
        fail("INVOICE_NOT_FOUND", 404)
    article = locked_article(db, hint.article_id)
    owner(article, user)
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
    if (
        article.status != "APPROVED"
        or invoice.status != "OPEN"
        or data.amount_minor != invoice.amount_minor
        or data.paid_at > db_now(db)
    ):
        fail("PAYMENT_NOT_ALLOWED")
    clean_file(db, data.proof_file_id, user.id, "PROOF", article.id)
    attempt = PaymentAttempt(
        invoice_id=invoice.id,
        submitted_by=user.id,
        reference_normalized=normalize_reference(data.reference),
        paid_at=data.paid_at,
        amount_minor=data.amount_minor,
        proof_file_id=data.proof_file_id,
    )
    db.add(attempt)
    db.flush()
    transition(db, article, "PAID", "PAYMENT_SUBMITTED", user)
    emit(db, article.id, "PAYMENT_SUBMITTED", admins(db), f"payment:{attempt.id}")
    return attempt


def verify(db, attempt_id, user, data):
    require_role(db, user, "ADMIN")
    article, invoice, attempt = payment_locks(db, attempt_id)
    if user.id in (article.author_id, attempt.submitted_by):
        fail("SELF_VERIFICATION_FORBIDDEN", 403)
    if (
        article.status != "PAID"
        or invoice.status != "OPEN"
        or attempt.status != "SUBMITTED"
        or attempt.amount_minor != invoice.amount_minor
        or not data.receipt_confirmed
        or normalize_reference(data.reference) != attempt.reference_normalized
    ):
        fail("PAYMENT_VERIFICATION_FAILED")
    clean_file(db, attempt.proof_file_id, attempt.submitted_by, "PROOF", article.id)
    attempt.status, attempt.verified_by, attempt.verified_at = "VERIFIED", user.id, db_now(db)
    attempt.receipt_note = data.receipt_note
    invoice.status = "PAID"
    transition(db, article, "PAYMENT_APPROVED", "PAYMENT_APPROVED", user)
    db.flush()
    audit(db, user, "VERIFY_PAYMENT", attempt)
    emit(db, article.id, "PAYMENT_VERIFIED", [article.author_id], f"verified:{attempt.id}")
    return attempt


def reject(db, attempt_id, user, reason):
    require_role(db, user, "ADMIN")
    article, invoice, attempt = payment_locks(db, attempt_id)
    if user.id == article.author_id:
        fail("SELF_VERIFICATION_FORBIDDEN", 403)
    if article.status != "PAID" or attempt.status != "SUBMITTED" or invoice.status != "OPEN":
        fail("PAYMENT_ALREADY_DECIDED")
    attempt.status, attempt.rejection_reason = "REJECTED", reason
    transition(db, article, "APPROVED", "PAYMENT_REJECTED", user)
    audit(db, user, "REJECT_PAYMENT", attempt)
    emit(db, article.id, "PAYMENT_REJECTED", [article.author_id], f"rejected:{attempt.id}")
    return attempt
