import base64
import json
import uuid
from datetime import datetime

from sqlalchemy import literal, tuple_

from app.api.serialization import record
from app.core.errors import fail


def page(db, model, query, limit=25, cursor=None, exclude=()):
    if cursor:
        try:
            stamp, key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            query = query.where(
                tuple_(model.created_at, model.id)
                > tuple_(literal(datetime.fromisoformat(stamp)), literal(uuid.UUID(key)))
            )
        except (ValueError, TypeError, KeyError):
            fail("INVALID_CURSOR", 422)
    rows = list(db.scalars(query.order_by(model.created_at, model.id).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        base64.urlsafe_b64encode(
            json.dumps([rows[-1].created_at.isoformat(), str(rows[-1].id)]).encode()
        ).decode()
        if more
        else None
    )
    return {"items": [record(row, exclude) for row in rows], "next_cursor": next_cursor}
