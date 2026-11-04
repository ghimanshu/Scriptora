from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None
    is_read: bool
    href: str | None


class NotificationSummary(BaseModel):
    unread_count: int
    total_count: int
    items: list[NotificationItem]


class NotificationPage(NotificationSummary):
    next_cursor: str | None


class ReadAllResult(BaseModel):
    updated_count: int
    unread_count: int
