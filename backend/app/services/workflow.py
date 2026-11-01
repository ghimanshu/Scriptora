import uuid

from sqlalchemy import delete, func, select

from app.api.deps import require_role, roles
from app.core.errors import fail
from app.db.session import db_now
from app.models.articles import Article, ArticleSubject, ArticleVersion, File, VersionAuthor
from app.models.reviews import Assignment, Review, ReviewComment, ReviewRound, RevisionResponse
from app.models.taxonomy import Outlet, PublicationType, Subject, Template
from app.models.users import User
from app.repositories.articles import expected, locked_article
from app.services.assignments import capacity, eligible, new_assignment, pool, transition
from app.services.notifications import admins, emit


def owner(article, user):
    if not article or article.status == "DELETED" or article.author_id != user.id:
        fail("ARTICLE_NOT_FOUND", 404)


def can_read(db, article, user):
    if not article or article.status == "DELETED":
        fail("ARTICLE_NOT_FOUND", 404)
    if article.author_id == user.id:
        return
    if article.status == "DRAFT":
        fail("ARTICLE_NOT_FOUND", 404)
    if "ADMIN" in roles(db, user):
        return
    if article.status == "SUBMITTED" and eligible(db, user, article):
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


def validate_classification(db, subject_id, outlet_id, template_id, publication_type_id=None):
    subject = db.get(Subject, subject_id) if subject_id else None
    outlet = db.get(Outlet, outlet_id) if outlet_id else None
    template = db.get(Template, template_id) if template_id else None
    kind = db.get(PublicationType, outlet.type_id) if outlet else None
    if (
        (subject_id and (not subject or not subject.active))
        or not outlet
        or not outlet.active
        or not template
        or not template.active
        or template.outlet_id != outlet.id
        or not kind
        or not kind.active
        or (publication_type_id and publication_type_id != outlet.type_id)
    ):
        fail("INVALID_CLASSIFICATION", 422)
    return subject, outlet, template


def update_draft_classification(db, article, version, data):
    changed = data.model_fields_set
    subject_id = (
        data.primary_subject_id if "primary_subject_id" in changed else article.primary_subject_id
    )
    outlet_id = data.outlet_id if "outlet_id" in changed else article.outlet_id
    template_id = data.template_id if "template_id" in changed else article.template_id
    kind_id = data.publication_type_id if "publication_type_id" in changed else None
    if "publication_type_id" in changed and kind_id is None:
        fail("INVALID_CLASSIFICATION", 422)
    subject, outlet, template = validate_classification(
        db, subject_id, outlet_id, template_id, kind_id
    )
    old_subject = article.primary_subject_id
    if old_subject and old_subject != subject_id:
        db.execute(
            delete(ArticleSubject).where(
                ArticleSubject.article_id == article.id, ArticleSubject.subject_id == old_subject
            )
        )
    if subject and not db.get(ArticleSubject, (article.id, subject.id)):
        db.add(ArticleSubject(article_id=article.id, subject_id=subject.id))
    article.primary_subject_id = subject.id if subject else None
    article.outlet_id, article.template_id = outlet.id, template.id
    version.template_id = template.id


def create_draft(db, user, data):
    require_role(db, user, "AUTHOR")
    subject, outlet, template = validate_classification(
        db, data.primary_subject_id, data.outlet_id, data.template_id, data.publication_type_id
    )
    article = Article(
        tracking_number="ART-" + uuid.uuid4().hex.upper(),
        author_id=user.id,
        primary_subject_id=subject.id if subject else None,
        outlet_id=outlet.id,
        template_id=template.id,
    )
    db.add(article)
    db.flush()
    if subject:
        db.add(ArticleSubject(article_id=article.id, subject_id=subject.id))
    version = create_version(db, article, user, data)
    article.current_version_id = version.id
    return article


def create_version(db, article, user, data):
    owner(article, user)
    if article.status not in ("DRAFT", "REJECTED"):
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
    if file and file.scan_status == "PENDING":
        fail("FILE_SCAN_PENDING", 409)
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
    if not article.primary_subject_id:
        fail("SUBJECT_REQUIRED", 422)
    subject = db.get(Subject, article.primary_subject_id)
    if not subject or not subject.active:
        fail("INVALID_CLASSIFICATION", 422)
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
        fail(
            "WORD_COUNT_OUTSIDE_TEMPLATE",
            422,
            details={
                "word_count": count,
                "min_words": rules.get("min_words", 1),
                "max_words": rules.get("max_words", 100000),
            },
        )
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
    if article.status != ("REJECTED" if revision else "DRAFT"):
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
                Review.version_id == article.current_version_id,
                Review.decision == "REQUEST_REVISION",
                Review.submitted_at.is_not(None),
            )
            .order_by(Review.submitted_at.desc())
            .limit(1)
        )
        if not predecessor:
            fail("REVIEW_FEEDBACK_REQUIRED", 409)
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
            select(User)
            .where(User.id == predecessor.reviewer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if eligible(db, reviewer, article) and capacity(db, reviewer):
            new_assignment(db, article, reviewer, db_now(db))
            return article
        emit(
            db,
            article.id,
            "REVISION_REVIEWER_UNAVAILABLE",
            admins(db),
            f"revision-reviewer-unavailable:{round.id}",
            {
                "title": "Revision needs a reviewer",
                "message": "The previous reviewer cannot take this revision. Assign an eligible reviewer.",
                "path": f"/admin/articles/{article.id}",
                "previous_reviewer_id": str(predecessor.reviewer_id),
            },
        )
    pool(db, article)
    return article
