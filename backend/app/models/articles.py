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


class File(Entity, Base):
    __tablename__ = "files"
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("articles.id", use_alter=True), index=True
    )
    kind: Mapped[str]
    storage_key: Mapped[str] = mapped_column(unique=True)
    sha256: Mapped[str]
    size_bytes: Mapped[int]
    content_type: Mapped[str]
    scan_status: Mapped[str] = mapped_column(default="PENDING", index=True)
    scan_attempts: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size"),
        CheckConstraint(
            "scan_status IN ('PENDING','CLEAN','QUARANTINED','FAILED')", name="scan_state"
        ),
        CheckConstraint("kind IN ('MANUSCRIPT','PROOF','ANNOTATION')", name="kind"),
    )


class Article(Entity, Base):
    __tablename__ = "articles"
    tracking_number: Mapped[str] = mapped_column(unique=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    primary_subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"), index=True)
    outlet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outlets.id"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id"))
    status: Mapped[str] = mapped_column(default="DRAFT")
    current_version_id: Mapped[uuid.UUID | None]
    approved_version_id: Mapped[uuid.UUID | None]
    current_round_id: Mapped[uuid.UUID | None]
    lock_version: Mapped[int] = mapped_column(default=1)
    pool_generation: Mapped[int] = mapped_column(default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','REVIEWED','APPROVED','PUBLISH')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["article_versions.article_id", "article_versions.id"],
            use_alter=True,
            name="fk_article_current_version",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["id", "approved_version_id"],
            ["article_versions.article_id", "article_versions.id"],
            use_alter=True,
            name="fk_article_approved_version",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["id", "current_round_id"],
            ["review_rounds.article_id", "review_rounds.id"],
            use_alter=True,
            name="fk_article_current_round",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "ix_article_subject_queue",
            "primary_subject_id",
            "submitted_at",
            "id",
            postgresql_where=text("status = 'SUBMITTED'"),
        ),
    )


class ArticleVersion(Entity, Base):
    __tablename__ = "article_versions"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    version_number: Mapped[int]
    data: Mapped[dict] = mapped_column("metadata", JSONB)
    manuscript_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        UniqueConstraint("article_id", "id"),
        UniqueConstraint("article_id", "version_number"),
    )


class VersionAuthor(Entity, Base):
    __tablename__ = "version_authors"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_versions.id"), index=True)
    sequence: Mapped[int]
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str]
    affiliation: Mapped[str]
    email: Mapped[str]
    __table_args__ = (UniqueConstraint("version_id", "sequence"),)


class ArticleSubject(Base):
    __tablename__ = "article_subjects"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"), primary_key=True)
