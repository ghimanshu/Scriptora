from sqlalchemy import select
from test_workflow import setup_article

from app.models.articles import ArticleVersion, File
from app.models.reviews import Assignment, ReviewComment
from app.models.users import User
from app.schemas.articles import Author, Manuscript, Resubmit, VersionInput
from app.schemas.reviews import Comment, Feedback
from app.services.assignments import claim, lock_assignment, transition
from app.services.reviews import save_review
from app.services.workflow import create_version, submit


def test_revision_reservation_preserves_resubmission_deadline(pg, monkeypatch):
    article, reviewers = setup_article(pg)
    assignment = claim(pg, article.id, reviewers[0], article.lock_version)
    review = save_review(
        pg,
        assignment.id,
        reviewers[0],
        Feedback(
            decision="REQUEST_REVISION",
            comments="Please clarify methods",
            checklist={"format": True},
            numbered_comments=[Comment(text="Add methods", section_ref="Methods")],
        ),
    )
    pg.commit()
    author = pg.get(User, article.author_id)
    file = File(
        owner_user_id=author.id,
        article_id=article.id,
        kind="MANUSCRIPT",
        storage_key="revision-test",
        sha256="c" * 64,
        size_bytes=100,
        content_type="application/pdf",
        scan_status="CLEAN",
    )
    pg.add(file)
    pg.flush()
    metadata = Manuscript(
        title="Revised article",
        abstract="Test abstract",
        keywords=["science"],
        authors=[Author(name="Author", affiliation="Test University", email=author.email)],
        declarations={"originality": True, "copyright": True, "conflict": True},
    )
    version = create_version(
        pg, article, author, VersionInput(metadata=metadata, manuscript_file_id=file.id)
    )
    comment = pg.scalar(select(ReviewComment).where(ReviewComment.review_id == review.id))
    monkeypatch.setattr("app.services.files.word_count", lambda _: 150)
    submit(
        pg,
        article.id,
        author,
        Resubmit(
            new_version_id=version.id,
            responses={comment.id: "Methods added"},
            expected_version=article.lock_version,
        ),
        revision=True,
    )
    pg.commit()
    reserved = pg.scalar(select(Assignment).where(Assignment.state == "RESERVED"))
    assert reserved.reviewer_id == reviewers[0].id
    assert article.status == "SUBMITTED"
    due = reserved.due_at
    article, reserved, now = lock_assignment(pg, reserved.id, reviewers[0], False)
    reserved.state, reserved.started_at = "ACTIVE", now
    transition(pg, article, "IN_REVIEW", "STARTED", reviewers[0])
    pg.commit()
    assert reserved.due_at == due
    assert article.current_version_id == version.id
    assert len(list(pg.scalars(select(ArticleVersion)))) == 2
