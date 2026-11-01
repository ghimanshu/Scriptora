from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.schemas.reviews import Reason


class Subjects(BaseModel):
    subject_ids: list[UUID] = Field(max_length=100)


class Availability(BaseModel):
    available: bool


class UserUpdate(Reason):
    active: bool
    roles: list[Literal["ADMIN", "AUTHOR", "REVIEWER"]]


class Extend(Reason):
    new_due_at: AwareDatetime


class Reassign(Reason):
    reviewer_id: UUID | None = None
    expected_version: int = Field(ge=1)


class Policy(BaseModel):
    review_duration_hours: int = Field(default=120, ge=120, le=120)
    publication_fee_minor: int = Field(default=250000, gt=0)
    max_live_assignments: int = Field(default=5, gt=0, le=100)
    payment_instructions: str = Field(min_length=5, max_length=4000)


class DeleteArticle(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
