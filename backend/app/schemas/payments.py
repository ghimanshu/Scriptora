from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field


class PaymentInput(BaseModel):
    amount_minor: int = Field(gt=0)
    reference: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9 -]+$")
    paid_at: AwareDatetime
    proof_file_id: UUID


class Verify(BaseModel):
    reference: str = Field(min_length=3, max_length=100)
    receipt_note: str = Field(min_length=5, max_length=2000)
    receipt_confirmed: bool


class Publish(BaseModel):
    issue_id: UUID | None = None
    approved_version_id: UUID
    final_file_id: UUID
    slug: str = Field(min_length=3, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=500)
    public_authors: list[str] = Field(min_length=1, max_length=100)


class VerifyPublish(Publish):
    payment_attempt_id: UUID
    verification: Verify
