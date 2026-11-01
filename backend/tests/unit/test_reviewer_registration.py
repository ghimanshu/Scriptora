from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import auth
from app.models.users import ReviewerProfile, UserRole
from app.schemas.auth import Register


def test_registration_defaults_to_author_and_disallows_admin():
    values = dict(email="user@example.com", display_name="User", password="long enough password")
    assert Register(**values).role == "AUTHOR"
    with pytest.raises(ValidationError):
        Register(**values, role="ADMIN")


@pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER"])
def test_registration_creates_requested_role_and_pending_profile(monkeypatch, role):
    monkeypatch.setattr(auth, "throttle", Mock())
    monkeypatch.setattr(auth, "one_time", Mock())
    monkeypatch.setattr(auth, "hash_password", lambda value: "hashed")
    emit = Mock()
    monkeypatch.setattr(auth, "emit", emit)
    monkeypatch.setattr(auth, "admins", lambda db: ["admin-id"])
    db = Mock()
    db.scalar.return_value = None
    auth.register(
        Register(
            email="user@example.com",
            display_name="User",
            password="long enough password",
            role=role,
        ),
        SimpleNamespace(client=None),
        db,
    )
    added = [call.args[0] for call in db.add.call_args_list]
    assert next(row for row in added if isinstance(row, UserRole)).role == role
    profiles = [row for row in added if isinstance(row, ReviewerProfile)]
    assert len(profiles) == (1 if role == "REVIEWER" else 0)
    if profiles:
        assert profiles[0].approved is False
        auth.one_time.assert_not_called()
        assert emit.call_args.args[2:4] == ("REVIEWER_APPLICATION", ["admin-id"])
        assert emit.call_args.args[5]["applicant_email"] == "user@example.com"
    else:
        auth.one_time.assert_called_once()
        emit.assert_not_called()


@pytest.mark.parametrize("approved", [None, False, True])
def test_only_approved_reviewer_can_sign_in(monkeypatch, approved):
    monkeypatch.setattr(auth, "roles", lambda db, user: {"REVIEWER"})
    db = Mock()
    db.get.return_value = (
        None if approved is None else SimpleNamespace(approved=approved, rejected=False)
    )
    user = SimpleNamespace(id="reviewer")
    if approved:
        auth.require_reviewer_approval(db, user)
    else:
        with pytest.raises(HTTPException) as error:
            auth.require_reviewer_approval(db, user)
        assert error.value.status_code == 403
        assert error.value.detail["code"] == "REVIEWER_APPROVAL_PENDING"


@pytest.mark.parametrize("approved", [False, True])
def test_login_enforces_approval_before_issuing_session(monkeypatch, approved):
    monkeypatch.setattr(auth, "throttle", Mock())
    monkeypatch.setattr(auth, "verify_password", lambda *args: True)
    monkeypatch.setattr(auth, "roles", lambda db, user: {"REVIEWER"})
    issue = Mock(return_value={"access_token": "approved-session"})
    monkeypatch.setattr(auth, "issue_session", issue)
    db = Mock()
    db.scalar.return_value = SimpleNamespace(
        id="reviewer", password_hash="hash", active=True, email_verified_at=True
    )
    db.get.return_value = SimpleNamespace(approved=approved, rejected=False)
    data = auth.Login(email="reviewer@example.com", password="password")
    if approved:
        assert auth.login(data, SimpleNamespace(client=None), db) == issue.return_value
        issue.assert_called_once()
    else:
        with pytest.raises(HTTPException) as error:
            auth.login(data, SimpleNamespace(client=None), db)
        assert error.value.detail["code"] == "REVIEWER_APPROVAL_PENDING"
        issue.assert_not_called()


@pytest.mark.parametrize("approved", [False, True])
def test_rejected_reviewers_are_blocked(monkeypatch, approved):
    monkeypatch.setattr(auth, "roles", lambda db, user: {"REVIEWER"})
    db = Mock()
    db.get.return_value = SimpleNamespace(approved=approved, rejected=True)
    with pytest.raises(HTTPException) as error:
        auth.require_reviewer_approval(db, SimpleNamespace(id="reviewer"))
    assert error.value.detail["code"] == "REVIEWER_APPLICATION_REJECTED"


@pytest.mark.parametrize("approve", [False, True])
@pytest.mark.parametrize("verified", [False, True])
def test_admin_decides_unverified_application_and_notifies_reviewer(monkeypatch, approve, verified):
    from app.api.v1 import admin
    from app.schemas.reviews import Reason

    target = SimpleNamespace(id="reviewer", active=True, email_verified_at=verified)
    profile = SimpleNamespace(approved=False, rejected=False, approved_by=None)
    db = Mock()
    db.scalar.side_effect = [target, profile]
    monkeypatch.setattr(admin, "roles", lambda db, user: {"REVIEWER"})
    for name in ("audit", "emit", "one_time"):
        monkeypatch.setattr(admin, name, Mock())
    result = admin.decide_reviewer(
        db,
        "reviewer",
        Reason(reason="Qualifications reviewed"),
        SimpleNamespace(id="admin"),
        approve,
    )
    assert result == {"approved": approve, "rejected": not approve}
    assert profile.approved == approve
    assert profile.rejected == (not approve)
    if approve and not verified:
        admin.one_time.assert_called_once()
        assert admin.one_time.call_args.kwargs["event_kind"] == "REVIEWER_APPROVED"
        admin.emit.assert_not_called()
    else:
        assert admin.emit.call_args.args[2] == (
            "REVIEWER_APPROVED" if approve else "REVIEWER_REJECTED"
        )
        assert admin.emit.call_args.args[3] == ["reviewer"]
        admin.one_time.assert_not_called()


@pytest.mark.parametrize("approved,rejected", [(True, False), (False, True)])
def test_completed_decision_cannot_be_overwritten(monkeypatch, approved, rejected):
    from app.api.v1 import admin
    from app.schemas.reviews import Reason

    db = Mock()
    db.scalar.side_effect = [
        SimpleNamespace(id="reviewer", active=True),
        SimpleNamespace(approved=approved, rejected=rejected),
    ]
    emit = Mock()
    monkeypatch.setattr(admin, "emit", emit)
    with pytest.raises(HTTPException) as error:
        admin.decide_reviewer(
            db, "reviewer", Reason(reason="Reviewed"), SimpleNamespace(id="admin"), not approved
        )
    assert error.value.status_code == 409
    emit.assert_not_called()


def test_reviewer_email_templates_include_review_link_and_decision_reason():
    from app.workers.outbox import event_body

    body = event_body(
        "REVIEWER_APPLICATION",
        {"applicant_name": "Reviewer", "applicant_email": "r@example.com"},
        "https://app.example",
    )
    assert "r@example.com" in body
    assert "https://app.example/admin/users" in body
    for kind in ("REVIEWER_APPROVED", "REVIEWER_REJECTED"):
        body = event_body(
            kind,
            {"message": "Application decision", "reason": "Reviewed expertise"},
            "https://app.example",
        )
        assert "Reviewed expertise" in body
