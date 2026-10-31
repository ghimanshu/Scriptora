import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(primary_key=True)
    __table_args__ = (CheckConstraint("role IN ('AUTHOR','REVIEWER','ADMIN')", name="role"),)


class ReviewerProfile(Base):
    __tablename__ = "reviewer_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    approved: Mapped[bool] = mapped_column(default=False)
    available: Mapped[bool] = mapped_column(default=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ReviewerSubject(Base):
    __tablename__ = "reviewer_subjects"
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"), primary_key=True)


class ReviewerConflict(Entity, Base):
    __tablename__ = "reviewer_conflicts"
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("articles.id"))
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    __table_args__ = (
        CheckConstraint("(article_id IS NULL) <> (author_user_id IS NULL)", name="one_target"),
    )


class AuthSession(Entity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(unique=True)
    token_family_id: Mapped[uuid.UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OneTimeToken(Entity, Base):
    __tablename__ = "one_time_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str]
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int]
    resets_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
