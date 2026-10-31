import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class ReviewRound(Entity, Base):
    __tablename__ = "review_rounds"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_versions.id"))
    round_number: Mapped[int]
    predecessor_review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", use_alter=True)
    )
    __table_args__ = (
        UniqueConstraint("article_id", "id"),
        UniqueConstraint("article_id", "round_number"),
    )


class Assignment(Entity, Base):
    __tablename__ = "review_assignments"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    round_id: Mapped[uuid.UUID]
    version_id: Mapped[uuid.UUID]
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str]
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_hours: Mapped[int]
    end_reason: Mapped[str | None]
    __table_args__ = (
        ForeignKeyConstraint(
            ["article_id", "version_id"], ["article_versions.article_id", "article_versions.id"]
        ),
        ForeignKeyConstraint(
            ["article_id", "round_id"], ["review_rounds.article_id", "review_rounds.id"]
        ),
        CheckConstraint(
            "state IN ('RESERVED','ACTIVE','COMPLETED','EXPIRED','RELEASED','REVOKED')",
            name="state",
        ),
        CheckConstraint("duration_hours > 0 AND due_at > assigned_at", name="duration"),
        Index(
            "uq_article_live_assignment",
            "article_id",
            unique=True,
            postgresql_where=text("state IN ('RESERVED','ACTIVE')"),
        ),
        Index(
            "ix_assignment_due", "due_at", postgresql_where=text("state IN ('RESERVED','ACTIVE')")
        ),
    )


class Review(Entity, Base):
    __tablename__ = "reviews"
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_assignments.id"), unique=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_versions.id"))
    decision: Mapped[str]
    comments: Mapped[str]
    checklist: Mapped[dict] = mapped_column(JSONB)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("decision IN ('REQUEST_REVISION','APPROVE')", name="decision"),
    )


class ReviewComment(Entity, Base):
    __tablename__ = "review_comments"
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), index=True)
    sequence: Mapped[int]
    section_ref: Mapped[str]
    text: Mapped[str]
    required: Mapped[bool]
    __table_args__ = (UniqueConstraint("review_id", "sequence"),)


class RevisionResponse(Entity, Base):
    __tablename__ = "revision_responses"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_versions.id"), index=True)
    comment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_comments.id"))
    response_text: Mapped[str]
    __table_args__ = (UniqueConstraint("version_id", "comment_id"),)


class StatusHistory(Entity, Base):
    __tablename__ = "article_status_history"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    old_status: Mapped[str]
    new_status: Mapped[str]
    event_type: Mapped[str]
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(default="")
