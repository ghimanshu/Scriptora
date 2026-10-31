"""Emit a contract for the frontend's OpenAPI TypeScript generator."""
import json
from pathlib import Path
from app.main import app
Path("var").mkdir(exist_ok=True)
Path("var/openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
