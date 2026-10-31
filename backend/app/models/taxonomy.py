import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class Subject(Entity, Base):
    __tablename__ = "subjects"
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)


class PublicationType(Entity, Base):
    __tablename__ = "publication_types"
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)


class Outlet(Entity, Base):
    __tablename__ = "outlets"
    type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publication_types.id"), index=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)


class Template(Entity, Base):
    __tablename__ = "templates"
    outlet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outlets.id"), index=True)
    version: Mapped[int]
    validation_schema: Mapped[dict] = mapped_column(JSONB)
    instructions: Mapped[str] = mapped_column(default="")
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint("outlet_id", "version"),)


class SettingsVersion(Entity, Base):
    __tablename__ = "settings_versions"
    version: Mapped[int] = mapped_column(unique=True)
    values: Mapped[dict] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Issue(Entity, Base):
    __tablename__ = "issues"
    outlet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outlets.id"), index=True)
    volume: Mapped[str]
    issue_number: Mapped[str]
    label: Mapped[str]
    __table_args__ = (UniqueConstraint("outlet_id", "volume", "issue_number"),)
