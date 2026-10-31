import uuid

from sqlalchemy import func, select

from app.api.deps import require_role, roles
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import Article, ArticleVersion, File, VersionAuthor
from app.models.reviews import Assignment, Review, ReviewComment, ReviewRound, RevisionResponse
from app.models.taxonomy import Outlet, Subject, Template
from app.models.users import User
from app.repositories.articles import expected, locked_article
from app.services.assignments import capacity, eligible, new_assignment, pool, transition
from app.services.notifications import admins, emit


def owner(article, user):
    if article.author_id != user.id:
        fail("ARTICLE_NOT_FOUND", 404)


def can_read(db, article, user):
    if article.author_id == user.id or "ADMIN" in roles(db, user):
        return
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.article_id == article.id,
            Assignment.reviewer_id == user.id,
            Assignment.state.in_(("ACTIVE", "RESERVED")),
            Assignment.due_at > db_now(db),
        )
    )
    if not assignment or not eligible(db, user, article, require_available=False):
        fail("ARTICLE_NOT_FOUND", 404)


def create_draft(db, user, data):
    require_role(db, user, "AUTHOR")
    subject, outlet, template = (
        db.get(Subject, data.primary_subject_id),
        db.get(Outlet, data.outlet_id),
        db.get(Template, data.template_id),
    )
    if (
        not subject
        or not subject.active
        or not outlet
        or not outlet.active
        or not template
        or not template.active
        or template.outlet_id != outlet.id
    ):
        fail("INVALID_CLASSIFICATION", 422)
    article = Article(
        tracking_number="ART-" + uuid.uuid4().hex.upper(),
        author_id=user.id,
        primary_subject_id=subject.id,
        outlet_id=outlet.id,
        template_id=template.id,
    )
    db.add(article)
    db.flush()
    version = create_version(db, article, user, data)
    article.current_version_id = version.id
    return article


def create_version(db, article, user, data):
    owner(article, user)
    if article.status not in ("DRAFT", "REVIEWED"):
        fail("VERSION_CREATION_FORBIDDEN")
    number = (
        db.scalar(
            select(func.max(ArticleVersion.version_number)).where(
                ArticleVersion.article_id == article.id
            )
        )
        or 0
    ) + 1
    version = ArticleVersion(
        article_id=article.id,
        version_number=number,
        template_id=article.template_id,
        data=data.metadata.model_dump(mode="json"),
        manuscript_file_id=data.manuscript_file_id,
    )
    db.add(version)
    db.flush()
    return version


def clean_file(db, file_id, user_id=None, kind=None, article_id=None):
    file = db.get(File, file_id) if file_id else None
    if (
        not file
        or file.scan_status != "CLEAN"
        or (user_id and file.owner_user_id != user_id)
        or (kind and file.kind != kind)
        or (article_id and file.article_id not in (None, article_id))
    ):
        fail("CLEAN_OWNED_FILE_REQUIRED", 422)
    return file


def freeze(db, article, version, user, now):
    metadata = version.data
    template = db.get(Template, article.template_id)
    rules = template.validation_schema
    if (
        version.submitted_at
        or not metadata.get("title", "").strip()
        or not metadata.get("authors")
        or not metadata.get("keywords")
        or (rules.get("abstract_required", True) and not metadata.get("abstract"))
    ):
        fail("MANUSCRIPT_INCOMPLETE", 422)
    if not all(
        metadata.get("declarations", {}).get(k) for k in ("originality", "copyright", "conflict")
    ):
        fail("DECLARATIONS_REQUIRED", 422)
    file = clean_file(db, version.manuscript_file_id, user.id, "MANUSCRIPT", article.id)
    from app.services.files import word_count

    count = word_count(file)
    if not rules.get("min_words", 1) <= count <= rules.get("max_words", 100000):
        fail("WORD_COUNT_OUTSIDE_TEMPLATE", 422)
    file.article_id = article.id
    for i, author in enumerate(metadata["authors"], 1):
        account = db.scalar(select(User).where(User.email == author["email"].lower()))
        db.add(
            VersionAuthor(
                version_id=version.id,
                sequence=i,
                user_id=account.id if account else None,
                name=author["name"],
                affiliation=author["affiliation"],
                email=author["email"].lower(),
            )
        )
    version.submitted_at = now
    article.current_version_id = version.id


def submit(db, article_id, user, command, revision=False):
    db.execute(select(func.pg_advisory_xact_lock_shared(17004)))
    article = locked_article(db, article_id)
    owner(article, user)
    expected(article, command.expected_version)
    if article.status != ("REVIEWED" if revision else "DRAFT"):
        fail("INVALID_TRANSITION")
    version = db.get(
        ArticleVersion, command.new_version_id if revision else article.current_version_id
    )
    if not version or version.article_id != article.id:
        fail("INVALID_VERSION", 422)
    predecessor = None
    if revision:
        predecessor = db.scalar(
            select(Review)
            .join(Assignment, Assignment.id == Review.assignment_id)
            .where(
                Assignment.article_id == article.id,
                Review.decision == "REQUEST_REVISION",
                Review.submitted_at.is_not(None),
            )
            .order_by(Review.submitted_at.desc())
            .limit(1)
        )
        comments = db.scalars(
            select(ReviewComment).where(ReviewComment.review_id == predecessor.id)
        ).all()
        valid = {c.id for c in comments}
        if set(command.responses) - valid or any(
            c.required and not command.responses.get(c.id, "").strip() for c in comments
        ):
            fail("COMMENT_RESPONSES_REQUIRED", 422)
        for comment_id, text in command.responses.items():
            db.add(
                RevisionResponse(version_id=version.id, comment_id=comment_id, response_text=text)
            )
    now = db_now(db)
    freeze(db, article, version, user, now)
    number = (
        db.scalar(
            select(func.max(ReviewRound.round_number)).where(ReviewRound.article_id == article.id)
        )
        or 0
    ) + 1
    round = ReviewRound(
        article_id=article.id,
        version_id=version.id,
        round_number=number,
        predecessor_review_id=predecessor.id if predecessor else None,
    )
    db.add(round)
    db.flush()
    article.current_round_id = round.id
    article.submitted_at = now
    transition(db, article, "SUBMITTED", "RESUBMITTED" if revision else "SUBMITTED", user)
    if predecessor:
        reviewer = db.scalar(
            select(User).where(User.id == predecessor.reviewer_id).with_for_update()
        )
        if eligible(db, reviewer, article) and capacity(db, reviewer):
            new_assignment(db, article, reviewer, db_now(db), reserved=True)
            return article
        emit(
            db, article.id, "RESERVATION_UNAVAILABLE", admins(db), f"reservation-failed:{round.id}"
        )
    pool(db, article)
    return article
