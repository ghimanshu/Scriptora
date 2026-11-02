from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.admin import Policy
from app.schemas.reviews import Feedback
from app.services import reviews


@pytest.mark.parametrize("instructions", ["", "     ", " abc "])
def test_payment_policy_requires_meaningful_instructions(instructions):
    with pytest.raises(ValidationError):
        Policy(payment_instructions=instructions)


def test_payment_policy_trims_instructions():
    assert (
        Policy(
            payment_instructions="  Pay using the configured bank account  "
        ).payment_instructions
        == "Pay using the configured bank account"
    )


@pytest.mark.parametrize("instructions", [None, "", "   "])
def test_approval_checks_payment_configuration_before_writes(monkeypatch, instructions):
    db = Mock()
    db.scalar.return_value = None
    assignment = SimpleNamespace(id="assignment")
    monkeypatch.setattr(
        reviews, "lock_assignment", lambda *args: (SimpleNamespace(), assignment, "now")
    )
    monkeypatch.setattr(reviews, "policy", lambda _: (1, {"payment_instructions": instructions}))
    with pytest.raises(HTTPException) as error:
        reviews.save_review(
            db,
            "assignment",
            SimpleNamespace(),
            Feedback(
                decision="APPROVE",
                comments="Accepted after review",
                checklist={"format_valid": True},
                required_changes_resolved=True,
            ),
        )
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "PAYMENT_DESTINATION_NOT_CONFIGURED"
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.execute.assert_not_called()
