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


class Invoice(Entity, Base):
    __tablename__ = "invoices"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    approved_version_id: Mapped[uuid.UUID]
    invoice_number: Mapped[str] = mapped_column(unique=True)
    amount_minor: Mapped[int]
    currency: Mapped[str] = mapped_column(default="INR")
    fee_policy_version: Mapped[int]
    instructions: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")
    __table_args__ = (
        UniqueConstraint("article_id", "approved_version_id"),
        ForeignKeyConstraint(
            ["article_id", "approved_version_id"],
            ["article_versions.article_id", "article_versions.id"],
        ),
        CheckConstraint("amount_minor > 0 AND currency = 'INR'", name="amount"),
        CheckConstraint("status IN ('OPEN','PAID','VOID')", name="status"),
    )


class PaymentAttempt(Entity, Base):
    __tablename__ = "payment_attempts"
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reference_normalized: Mapped[str]
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount_minor: Mapped[int]
    proof_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    status: Mapped[str] = mapped_column(default="SUBMITTED")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_note: Mapped[str | None]
    rejection_reason: Mapped[str | None]
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount"),
        CheckConstraint("status IN ('SUBMITTED','VERIFIED','REJECTED')", name="status"),
        Index(
            "uq_verified_invoice_payment",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'VERIFIED'"),
        ),
        Index(
            "uq_pending_invoice_payment",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'SUBMITTED'"),
        ),
        Index(
            "uq_verified_payment_reference",
            "reference_normalized",
            unique=True,
            postgresql_where=text("status = 'VERIFIED'"),
        ),
    )


class Publication(Entity, Base):
    __tablename__ = "publications"
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), unique=True)
    version_id: Mapped[uuid.UUID]
    slug: Mapped[str] = mapped_column(unique=True)
    issue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("issues.id"))
    final_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column("metadata", JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["article_id", "version_id"], ["article_versions.article_id", "article_versions.id"]
        ),
    )
