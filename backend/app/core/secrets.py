"""Authenticated encryption for short-lived outbox credentials."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def cipher():
    cfg = get_settings()
    key = (
        cfg.outbox_encryption_key
        or base64.urlsafe_b64encode(hashlib.sha256(cfg.jwt_signing_key.encode()).digest()).decode()
    )
    return Fernet(key.encode())


def seal(value):
    return cipher().encrypt(value.encode()).decode()


def unseal(value):
    return cipher().decrypt(value.encode()).decode()
