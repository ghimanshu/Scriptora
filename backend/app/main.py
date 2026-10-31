import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models as registered_models  # noqa: F401
from app.api.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging

cfg = get_settings()
configure_logging(cfg.log_level)
app = FastAPI(
    title=cfg.app_name,
    version="0.1.0",
    docs_url="/docs" if cfg.app_env != "production" else None,
    redoc_url=None,
)
app.include_router(router, prefix=cfg.api_prefix)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception("Request failed request_id=%s", request_id)
        response = JSONResponse(
            {"detail": {"code": "INTERNAL_ERROR"}, "request_id": request_id}, status_code=500
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    if not request.url.path.startswith(cfg.api_prefix + "/public/"):
        response.headers["Cache-Control"] = "no-store"
    return response
