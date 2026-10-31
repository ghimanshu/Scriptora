from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.repositories.articles import expected
from app.services import assignments


@pytest.mark.parametrize("offset,expires", [(-1, False), (0, True), (1, True)])
def test_deadline_boundary_and_expiry_deduplication(monkeypatch, offset, expires):
    due = datetime(2026, 10, 31, tzinfo=timezone.utc)
    article = SimpleNamespace(id="article", status="IN_REVIEW", lock_version=4)
    assignment = SimpleNamespace(
        id="assignment", state="ACTIVE", due_at=due, reviewer_id="reviewer"
    )
    article.author_id = "author"
    events, pools = Mock(), Mock()
    monkeypatch.setattr(assignments, "emit", events)
    monkeypatch.setattr(assignments, "pool", pools)
    monkeypatch.setattr(
        assignments, "transition", lambda db, a, state, event: setattr(a, "status", state)
    )
    now = due + timedelta(microseconds=offset)
    assert assignments.expire(Mock(), article, assignment, now) is expires
    if expires:
        assert assignment.state == "EXPIRED"
        assert article.status == "SUBMITTED"
        assert not assignments.expire(Mock(), article, assignment, now)
        events.assert_called_once()
        pools.assert_called_once()
    else:
        events.assert_not_called()


def test_stale_write_rejected():
    with pytest.raises(HTTPException) as error:
        expected(SimpleNamespace(lock_version=2), 1)
    assert error.value.status_code == 409
