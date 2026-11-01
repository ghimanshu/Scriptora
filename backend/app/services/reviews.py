from sqlalchemy import delete, select

from app.core.errors import fail
from app.models.payments import Invoice
from app.models.reviews import Review, ReviewComment
from app.services.assignments import lock_assignment, policy, transition
from app.services.notifications import emit


def save_review(db, assignment_id, user, data, final=True):
    article, assignment, now = lock_assignment(db, assignment_id, user)
    review = db.scalar(select(Review).where(Review.assignment_id == assignment.id))
    if review and review.submitted_at:
        fail("REVIEW_ALREADY_SUBMITTED")
    if (
        final
        and data.decision == "APPROVE"
        and (not data.required_changes_resolved or not all(data.checklist.values()))
    ):
        fail("APPROVAL_CHECKLIST_INCOMPLETE", 422)
    if final and data.decision == "REQUEST_REVISION" and not data.numbered_comments:
        fail("REVISION_COMMENTS_REQUIRED", 422)
    if not review:
        review = Review(
            assignment_id=assignment.id, reviewer_id=user.id, version_id=assignment.version_id
        )
        db.add(review)
    review.decision, review.comments, review.checklist = (
        data.decision,
        data.comments,
        data.checklist,
    )
    db.flush()
    db.execute(delete(ReviewComment).where(ReviewComment.review_id == review.id))
    for i, item in enumerate(data.numbered_comments, 1):
        db.add(ReviewComment(review_id=review.id, sequence=i, **item.model_dump()))
    if final:
        review.submitted_at = now
        assignment.state, assignment.completed_at = "COMPLETED", now
        accepted = data.decision == "APPROVE"
        transition(db, article, "APPROVED" if accepted else "REJECTED", data.decision, user)
        if accepted:
            version, settings = policy(db)
            if not settings.get("payment_instructions"):
                fail("PAYMENT_DESTINATION_NOT_CONFIGURED", 422)
            article.approved_version_id = article.current_version_id
            db.add(
                Invoice(
                    article_id=article.id,
                    approved_version_id=article.current_version_id,
                    invoice_number="INV-" + str(article.id),
                    amount_minor=settings["publication_fee_minor"],
                    currency="INR",
                    fee_policy_version=version,
                    instructions=settings["payment_instructions"],
                )
            )
        emit(
            db,
            article.id,
            "ARTICLE_APPROVED" if accepted else "ARTICLE_REJECTED",
            [article.author_id],
            f"review:{review.id}",
            {
                "title": "Article approved" if accepted else "Article changes requested",
                "message": (
                    "Your article is approved. Pay the publication fee and upload payment proof."
                    if accepted
                    else "Your article requires changes. Read the feedback, revise, and resubmit."
                ),
                "path": f"/author/articles/{article.id}",
                **(
                    {
                        "amount_minor": settings["publication_fee_minor"],
                        "currency": "INR",
                        "payment_instructions": settings["payment_instructions"],
                    }
                    if accepted
                    else {}
                ),
            },
        )
    return review
