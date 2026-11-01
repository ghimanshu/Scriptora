import pytest
from sqlalchemy import select
from test_workflow import setup_article

from app.models.articles import ArticleVersion, File
from app.models.notifications import OutboxEvent
from app.models.reviews import Assignment, ReviewComment, RevisionResponse
from app.models.users import ReviewerProfile, User, UserRole
from app.schemas.articles import Author, Manuscript, Resubmit, VersionInput
from app.schemas.reviews import Comment, Feedback
from app.services.assignments import claim
from app.services.reviews import save_review
from app.services.workflow import create_version, submit


def prepare_revision(pg, monkeypatch, replace_file=True):
    article, reviewers = setup_article(pg)
    author = pg.get(User, article.author_id)
    original_version = pg.get(ArticleVersion, article.current_version_id)
    original_file = File(
        owner_user_id=author.id,
        article_id=article.id,
        kind="MANUSCRIPT",
        storage_key="original-revision-test",
        sha256="a" * 64,
        size_bytes=100,
        content_type="application/pdf",
        scan_status="CLEAN",
    )
    pg.add(original_file)
    pg.flush()
    original_version.manuscript_file_id = original_file.id
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
    file = original_file
    if replace_file:
        file = File(
            owner_user_id=author.id,
            article_id=article.id,
            kind="MANUSCRIPT",
            storage_key="replacement-revision-test",
            sha256="c" * 64,
            size_bytes=100,
            content_type="application/pdf",
            scan_status="CLEAN",
        )
        pg.add(file)
        pg.flush()
    metadata = Manuscript(
        title="Revised article",
        abstract="Updated abstract",
        keywords=["science"],
        authors=[Author(name="Author", affiliation="Test University", email=author.email)],
        declarations={"originality": True, "copyright": True, "conflict": True},
    )
    version = create_version(
        pg, article, author, VersionInput(metadata=metadata, manuscript_file_id=file.id)
    )
    comment = pg.scalar(select(ReviewComment).where(ReviewComment.review_id == review.id))
    monkeypatch.setattr("app.services.files.word_count", lambda _: 150)
    command = Resubmit(
        new_version_id=version.id,
        responses={comment.id: "Methods added"},
        expected_version=article.lock_version,
    )
    return article, reviewers, author, assignment, original_version, version, command


@pytest.mark.parametrize("replace_file", [False, True])
def test_revision_returns_to_same_reviewer_with_new_five_day_deadline(
    pg, monkeypatch, replace_file
):
    article, reviewers, author, previous, original, version, command = prepare_revision(
        pg, monkeypatch, replace_file
    )
    previous_due = previous.due_at
    submit(pg, article.id, author, command, revision=True)
    pg.commit()
    assigned = pg.scalar(select(Assignment).where(Assignment.state == "ACTIVE"))
    assert assigned.reviewer_id == reviewers[0].id
    assert assigned.id != previous.id
    assert previous.state == "COMPLETED"
    assert previous.due_at == previous_due
    assert assigned.assigned_at >= article.submitted_at
    assert (assigned.due_at - assigned.assigned_at).total_seconds() == 5 * 24 * 3600
    assert article.status == "ASSIGNED"
    assert assigned.version_id == article.current_version_id == version.id
    assert original.data["title"] == "Test article"
    assert version.data["title"] == "Revised article"
    assert (original.manuscript_file_id != version.manuscript_file_id) == replace_file
    assert original.submitted_at is not None and version.submitted_at is not None
    assert pg.scalar(select(RevisionResponse)).response_text == "Methods added"
    assert len(list(pg.scalars(select(ArticleVersion)))) == 2


@pytest.mark.parametrize("unavailable", ["availability", "inactive", "approval"])
def test_revision_notifies_admin_when_previous_reviewer_cannot_take_it(
    pg, monkeypatch, unavailable
):
    article, reviewers, author, previous, original, version, command = prepare_revision(
        pg, monkeypatch
    )
    pg.add(UserRole(user_id=reviewers[1].id, role="ADMIN"))
    if unavailable == "inactive":
        reviewers[0].active = False
    else:
        profile = pg.get(ReviewerProfile, reviewers[0].id)
        if unavailable == "availability":
            profile.available = False
        else:
            profile.approved = False
    submit(pg, article.id, author, command, revision=True)
    pg.commit()
    assert article.status == "SUBMITTED"
    assert not pg.scalar(select(Assignment).where(Assignment.state == "ACTIVE"))
    notice = pg.scalar(
        select(OutboxEvent).where(OutboxEvent.type == "REVISION_REVIEWER_UNAVAILABLE")
    )
    assert notice.payload["recipients"] == [str(reviewers[1].id)]
    assert notice.payload["previous_reviewer_id"] == str(reviewers[0].id)
