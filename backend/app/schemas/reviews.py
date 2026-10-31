from typing import Literal

from pydantic import BaseModel, Field


class Comment(BaseModel):
    section_ref: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    required: bool = True


class Feedback(BaseModel):
    decision: Literal["REQUEST_REVISION", "APPROVE"]
    comments: str = Field(min_length=1, max_length=50000)
    checklist: dict[str, bool] = Field(min_length=1)
    numbered_comments: list[Comment] = Field(default_factory=list, max_length=200)
    required_changes_resolved: bool = False


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
