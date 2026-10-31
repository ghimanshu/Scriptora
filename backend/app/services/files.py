import hashlib
import io
import uuid
import zipfile
from pathlib import Path

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from app.core.errors import fail
from app.integrations.storage import storage
from app.models.articles import File


def validate_bytes(filename, content_type, data, kind):
    suffix = Path(filename or "").suffix.lower()
    types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    allowed = (".pdf", ".png", ".jpg", ".jpeg") if kind == "PROOF" else (".pdf", ".docx")
    if suffix not in allowed or content_type != types.get(suffix):
        fail("UNSUPPORTED_FILE_TYPE", 422)
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            fail("INVALID_PDF", 422)
        try:
            reader = PdfReader(io.BytesIO(data))
            if (
                reader.is_encrypted
                or len(reader.pages) > 1000
                or any(
                    x in data
                    for x in (
                        b"/JavaScript",
                        b"/JS",
                        b"/Launch",
                        b"/EmbeddedFile",
                        b"/OpenAction",
                        b"/AA",
                    )
                )
            ):
                fail("UNSAFE_PDF", 422)
        except Exception:
            fail("INVALID_OR_UNSAFE_PDF", 422)
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if (
                    sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024
                    or len(archive.infolist()) > 2000
                ):
                    fail("UNSAFE_ARCHIVE", 422)
                if "word/document.xml" not in archive.namelist() or any(
                    "vbaproject" in n.lower() or n.startswith("/") or ".." in n.split("/")
                    for n in archive.namelist()
                ):
                    fail("UNSAFE_DOCX", 422)
                fromstring(archive.read("word/document.xml"))
        except Exception:
            fail("INVALID_DOCX", 422)
    elif suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        fail("INVALID_PNG", 422)
    elif suffix in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        fail("INVALID_JPEG", 422)


def upload(db, user, kind, article_id, filename, content_type, data):
    if kind not in ("MANUSCRIPT", "PROOF", "ANNOTATION"):
        fail("INVALID_FILE_KIND", 422)
    validate_bytes(filename, content_type, data, kind)
    key = uuid.uuid4().hex
    storage().put(key, data)
    item = File(
        owner_user_id=user.id,
        article_id=article_id,
        kind=kind,
        storage_key=key,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        content_type=content_type,
    )
    db.add(item)
    db.flush()
    return item


def word_count(file):
    data = storage().get(file.storage_key)
    try:
        if file.content_type == "application/pdf":
            text = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = fromstring(archive.read("word/document.xml"))
                text = " ".join(n.text or "" for n in xml.iter() if n.tag.endswith("}t"))
        return len(text.split())
    except Exception:
        fail("MANUSCRIPT_TEXT_UNREADABLE", 422)
