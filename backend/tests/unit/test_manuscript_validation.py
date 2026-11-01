import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter

from app.services import files, workflow


def test_pdf_without_readable_text_has_actionable_error(monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    monkeypatch.setattr(files, "storage", lambda: SimpleNamespace(get=lambda _: buffer.getvalue()))
    with pytest.raises(HTTPException) as error:
        files.word_count(SimpleNamespace(storage_key="manuscript", content_type="application/pdf"))
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "MANUSCRIPT_TEXT_UNREADABLE"


def test_pdf_word_count_uses_all_pages(monkeypatch):
    monkeypatch.setattr(files, "storage", lambda: SimpleNamespace(get=lambda _: b"pdf"))
    monkeypatch.setattr(
        files,
        "PdfReader",
        lambda _: SimpleNamespace(
            pages=[
                SimpleNamespace(extract_text=lambda: "One two three"),
                SimpleNamespace(extract_text=lambda: "Four five"),
            ]
        ),
    )
    assert (
        files.word_count(SimpleNamespace(storage_key="manuscript", content_type="application/pdf"))
        == 5
    )


@pytest.mark.parametrize("count,valid", [(99, False), (100, True), (20000, True), (20001, False)])
def test_freeze_enforces_template_limits_with_count_details(monkeypatch, count, valid):
    db = Mock()
    db.get.return_value = SimpleNamespace(
        active=True, validation_schema={"min_words": 100, "max_words": 20000}
    )
    db.scalar.return_value = None
    file = SimpleNamespace(article_id=None)
    monkeypatch.setattr(workflow, "clean_file", lambda *args: file)
    monkeypatch.setattr(files, "word_count", lambda _: count)
    article = SimpleNamespace(
        id="article", template_id="template", primary_subject_id="subject", current_version_id=None
    )
    version = SimpleNamespace(
        id="version",
        submitted_at=None,
        manuscript_file_id="file",
        data={
            "title": "Article",
            "keywords": ["Science"],
            "abstract": "Abstract",
            "authors": [{"name": "Author", "affiliation": "Institute", "email": "a@example.com"}],
            "declarations": {"originality": True, "copyright": True, "conflict": True},
        },
    )
    if valid:
        workflow.freeze(db, article, version, SimpleNamespace(id="author"), "now")
        assert version.submitted_at == "now"
        assert file.article_id == article.id
    else:
        with pytest.raises(HTTPException) as error:
            workflow.freeze(db, article, version, SimpleNamespace(id="author"), "now")
        assert error.value.detail == {
            "code": "WORD_COUNT_OUTSIDE_TEMPLATE",
            "details": {
                "word_count": count,
                "min_words": 100,
                "max_words": 20000,
            },
        }
        assert version.submitted_at is None
        db.add.assert_not_called()
