"""Keep command effects and their cached response in the same transaction."""

import hashlib
import json
from datetime import timedelta

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import fail
from app.db.session import db_now, session_factory
from app.models.audit import IdempotencyKey


class IdempotentRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request):
            path = request.url.path
            if (
                request.method not in ("POST", "PUT", "PATCH", "DELETE")
                or "/auth/" in path
                or path.endswith("/files")
            ):
                return await original(request)
            key = request.headers.get("Idempotency-Key")
            if not key or len(key) > 200:
                fail("IDEMPOTENCY_KEY_REQUIRED", 400)
            from app.api.deps import current_user

            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                fail("AUTHENTICATION_REQUIRED", 401)
            body = await request.body()
            fingerprint = hashlib.sha256(body).hexdigest()
            route = request.method + ":" + path
            with session_factory()() as db:
                request.state.command_db = db
                db.info["request_id"] = getattr(request.state, "request_id", None)
                try:
                    user = current_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer", credentials=authorization[7:]
                        ),
                        db,
                    )
                    lock = int.from_bytes(
                        hashlib.sha256((str(user.id) + route + key).encode()).digest()[:8],
                        "big",
                        signed=True,
                    )
                    db.execute(select(func.pg_advisory_xact_lock(lock)))
                    cached = db.scalar(
                        select(IdempotencyKey).where(
                            IdempotencyKey.actor_id == user.id,
                            IdempotencyKey.route == route,
                            IdempotencyKey.key == key,
                        )
                    )
                    if cached and cached.expires_at > db_now(db):
                        if cached.request_hash != fingerprint:
                            fail("IDEMPOTENCY_PAYLOAD_MISMATCH")
                        return JSONResponse(cached.response_body, status_code=cached.response_code)
                    if cached:
                        db.delete(cached)
                        db.flush()
                    response = await original(request)
                    if response.status_code < 400:
                        payload = json.loads(bytes(response.body)) if response.body else {}
                        db.add(
                            IdempotencyKey(
                                actor_id=user.id,
                                route=route,
                                key=key,
                                request_hash=fingerprint,
                                response_code=response.status_code,
                                response_body=payload,
                                expires_at=db_now(db) + timedelta(days=1),
                            )
                        )
                        db.commit()
                    else:
                        db.rollback()
                    return response
                except IntegrityError:
                    db.rollback()
                    fail("CONFLICTING_WRITE")
                except Exception:
                    db.rollback()
                    raise

        return handle
