from sqlalchemy import select

from app.api.deps import require_role
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import ArticleVersion
from app.models.payments import Invoice, PaymentAttempt, Publication
from app.models.taxonomy import Issue
from app.repositories.articles import locked_article
from app.services.assignments import transition
from app.services.notifications import emit
from app.services.workflow import clean_file


def publish(db, article_id, user, data):
    require_role(db, user, "ADMIN")
    article = locked_article(db, article_id)
    invoice = db.scalar(select(Invoice).where(Invoice.article_id == article.id).with_for_update())
    if user.id == article.author_id:
        fail("SELF_PUBLICATION_FORBIDDEN", 403)
    if (
        article.status != "PAYMENT_APPROVED"
        or not invoice
        or invoice.status != "PAID"
        or data.approved_version_id != article.approved_version_id
        or invoice.approved_version_id != article.approved_version_id
    ):
        fail("PUBLICATION_GUARDS_FAILED")
    verified = db.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.invoice_id == invoice.id, PaymentAttempt.status == "VERIFIED"
        )
    )
    version = db.get(ArticleVersion, article.approved_version_id)
    if not verified or data.final_file_id != version.manuscript_file_id:
        fail("APPROVED_ARTIFACT_REQUIRED")
    file = clean_file(db, data.final_file_id, article.author_id, "MANUSCRIPT", article.id)
    if file.content_type != "application/pdf":
        fail("APPROVED_PDF_REQUIRED", 422)
    if data.issue_id:
        issue = db.get(Issue, data.issue_id)
        if not issue or issue.outlet_id != article.outlet_id:
            fail("ISSUE_OUTLET_MISMATCH", 422)
    now = db_now(db)
    publication = Publication(
        article_id=article.id,
        version_id=article.approved_version_id,
        slug=data.slug,
        final_file_id=file.id,
        issue_id=data.issue_id,
        published_by=user.id,
        published_at=now,
        data={
            "title": data.title,
            "authors": data.public_authors,
            "subject_id": str(article.primary_subject_id),
            "outlet_id": str(article.outlet_id),
        },
    )
    db.add(publication)
    article.published_at = now
    transition(db, article, "PUBLISH", "PUBLISHED", user)
    emit(db, article.id, "PUBLISHED", [article.author_id], f"published:{article.id}")
    return publication
