import os

os.environ.setdefault("JWT_SIGNING_KEY", "test-only-secret-at-least-thirty-two-characters")
os.environ.setdefault("APP_ENV", "test")

from pathlib import Path

Path("var").mkdir(exist_ok=True)
