import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.integrations.storage import LocalStorage
from app.services.files import normalize_kind, validate_bytes


def test_argon2id_and_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


@pytest.mark.parametrize(
    "values",
    [
        {"jwt_signing_key": "REPLACE_WITH_A_CRYPTOGRAPHIC_RANDOM_SECRET"},
        {"jwt_signing_key": "x" * 40, "app_env": "production"},
        {"jwt_signing_key": "x" * 40, "database_url": "sqlite:///unsafe.db"},
        {
            "jwt_signing_key": "x" * 40,
            "app_env": "production",
            "storage_driver": "s3",
            "scanner_driver": "bypass",
        },
    ],
)
def test_unsafe_configuration_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_private_storage_rejects_traversal(tmp_path, monkeypatch):
    from app.integrations import storage

    monkeypatch.setattr(
        storage, "get_settings", lambda: type("Cfg", (), {"local_storage_root": tmp_path})()
    )
    store = LocalStorage()
    with pytest.raises(ValueError):
        store.get("../secret")
    with pytest.raises(ValueError):
        store.get(str(tmp_path.parent / "secret"))
    store.put("immutable", b"safe")
    with pytest.raises(FileExistsError):
        store.put("immutable", b"replacement")


@pytest.mark.parametrize(
    "filename,mime,data,kind",
    [
        ("evil.pdf", "application/pdf", b"<script>alert(1)</script>", "MANUSCRIPT"),
        ("macro.docm", "application/octet-stream", b"PK", "MANUSCRIPT"),
        ("proof.png", "image/png", b"not an image", "PROOF"),
        ("proof.pdf", "image/png", b"%PDF-1.7", "PROOF"),
    ],
)
def test_invalid_uploads_rejected(filename, mime, data, kind):
    with pytest.raises(HTTPException) as error:
        validate_bytes(filename, mime, data, kind)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "submitted,expected",
    [
        ("MANUSCRIPT", "MANUSCRIPT"),
        ("manuscript", "MANUSCRIPT"),
        ("PROOF", "PROOF"),
        ("payment_proof", "PROOF"),
        ("annotation", "ANNOTATION"),
    ],
)
def test_upload_kind_is_normalized(submitted, expected):
    assert normalize_kind(submitted) == expected


def test_unknown_upload_kind_rejected():
    with pytest.raises(HTTPException) as error:
        normalize_kind("unknown")
    assert error.value.status_code == 422
