from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Author(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    affiliation: str = Field(min_length=1, max_length=300)
    email: EmailStr
    user_id: UUID | None = None


class Manuscript(BaseModel):
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=10000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    authors: list[Author] = Field(default_factory=list, max_length=100)
    declarations: dict[str, bool] = Field(default_factory=dict)


class Draft(BaseModel):
    publication_type_id: UUID | None = None
    primary_subject_id: UUID | None = None
    outlet_id: UUID
    template_id: UUID
    metadata: Manuscript
    manuscript_file_id: UUID | None = None


class VersionInput(BaseModel):
    metadata: Manuscript
    manuscript_file_id: UUID | None = None


class DraftUpdate(VersionInput):
    publication_type_id: UUID | None = None
    primary_subject_id: UUID | None = None
    outlet_id: UUID | None = None
    template_id: UUID | None = None


class Expected(BaseModel):
    expected_version: int = Field(ge=1)


class Resubmit(Expected):
    new_version_id: UUID
    responses: dict[UUID, str] = Field(default_factory=dict)
