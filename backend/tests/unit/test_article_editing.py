from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import articles
from app.schemas.articles import VersionInput


@pytest.mark.parametrize(
    "status,actions",
    [
        ("DRAFT", ["EDIT", "SUBMIT"]),
        ("REJECTED", ["RESUBMIT"]),
        ("SUBMITTED", []),
        ("ASSIGNED", []),
        ("APPROVED", ["VIEW_INVOICE"]),
        ("PUBLISH", ["VIEW_INVOICE"]),
        ("DELETED", []),
    ],
)
def test_actions_only_allow_editing_drafts_and_requested_revisions(status, actions):
    owner = SimpleNamespace(id=uuid4())
    article = SimpleNamespace(author_id=owner.id, status=status)
    assert articles.author_actions(article, owner) == actions
    assert articles.author_actions(article, SimpleNamespace(id=uuid4())) == []


@pytest.mark.parametrize("status", ["SUBMITTED", "ASSIGNED", "REJECTED", "APPROVED", "PUBLISH"])
def test_direct_draft_patch_is_blocked_after_submission(monkeypatch, status):
    user = SimpleNamespace(id=uuid4())
    article = SimpleNamespace(author_id=user.id, status=status, lock_version=1)
    monkeypatch.setattr(articles, "locked_article", lambda *args: article)
    db = Mock()
    with pytest.raises(HTTPException) as error:
        articles.edit(uuid4(), VersionInput(metadata={"title": "Changed"}), "1", user, db)
    assert error.value.detail["code"] == "DRAFT_REQUIRED"
    db.get.assert_not_called()


def test_owner_can_update_draft_and_preserve_version_metadata(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    article = SimpleNamespace(
        author_id=user.id, status="DRAFT", lock_version=1, current_version_id=uuid4()
    )
    version = SimpleNamespace(data={}, manuscript_file_id=None, lock_version=1)
    monkeypatch.setattr(articles, "locked_article", lambda *args: article)
    monkeypatch.setattr(articles, "record", lambda row: {"lock_version": row.lock_version})
    db = Mock()
    db.get.return_value = version
    result = articles.edit(
        uuid4(),
        VersionInput(
            metadata={
                "title": "Updated title",
                "abstract": "Updated abstract",
                "keywords": ["science"],
            }
        ),
        "1",
        user,
        db,
    )
    assert version.data["title"] == "Updated title"
    assert version.data["keywords"] == ["science"]
    assert result["lock_version"] == 2


@pytest.mark.parametrize(
    "status,submitted",
    [
        ("SUBMITTED", False),
        ("ASSIGNED", False),
        ("APPROVED", False),
        ("DRAFT", True),
        ("REJECTED", True),
    ],
)
def test_existing_submitted_version_is_immutable(monkeypatch, status, submitted):
    user = SimpleNamespace(id=uuid4())
    article = SimpleNamespace(id=uuid4(), author_id=user.id, status=status)
    version = SimpleNamespace(article_id=article.id, lock_version=1, submitted_at=submitted)
    monkeypatch.setattr(articles, "locked_article", lambda *args: article)
    db = Mock()
    db.get.return_value = version
    with pytest.raises(HTTPException) as error:
        articles.edit_version(
            article.id, uuid4(), VersionInput(metadata={"title": "Changed"}), "1", user, db
        )
    assert error.value.detail["code"] == "IMMUTABLE_VERSION"
