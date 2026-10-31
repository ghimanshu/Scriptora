import random
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.secrets import unseal
from app.db.session import db_now, session_factory
from app.integrations.email import send_email
from app.models.articles import Article
from app.models.notifications import EmailDelivery, Notification, OutboxEvent
from app.models.reviews import Assignment
from app.models.users import User
from app.repositories.assignments import LIVE
from app.repositories.outbox import claim_event
from app.services.assignments import eligible
from app.services.notifications import admins, emit


def run():
    factory = session_factory()
    with factory.begin() as db:
        event = claim_event(db)
        if not event:
            return
        event_id, lease = event.id, event.lease_until
    try:
        with factory.begin() as db:
            event = db.get(OutboxEvent, event_id)
            payload = event.payload
            targets = []
            for raw in payload.get("recipients", []):
                user = db.get(User, uuid.UUID(raw))
                if not user or not user.active:
                    continue
                if event.type == "AVAILABLE":
                    article = db.get(Article, event.aggregate_id)
                    live = db.scalar(
                        select(Assignment.id).where(
                            Assignment.article_id == article.id, Assignment.state.in_(LIVE)
                        )
                    )
                    if (
                        article.status != "SUBMITTED"
                        or article.pool_generation != payload["generation"]
                        or live
                        or not eligible(db, user, article)
                    ):
                        continue
                if event.type == "DEADLINE_REMINDER":
                    assignment = db.get(Assignment, uuid.UUID(payload["assignment_id"]))
                    if assignment.state not in LIVE or assignment.due_at <= db_now(db):
                        continue
                safe = {
                    k: v for k, v in payload.items() if k not in ("encrypted_token", "recipients")
                }
                db.execute(
                    insert(Notification)
                    .values(
                        id=uuid.uuid4(),
                        recipient_id=user.id,
                        event_id=event.id,
                        type=event.type,
                        payload=safe,
                    )
                    .on_conflict_do_nothing()
                )
                db.execute(
                    insert(EmailDelivery)
                    .values(
                        id=uuid.uuid4(),
                        recipient_id=user.id,
                        event_id=event.id,
                        template_key=event.type,
                        state="PENDING",
                    )
                    .on_conflict_do_nothing()
                )
                delivery = db.scalar(
                    select(EmailDelivery).where(
                        EmailDelivery.event_id == event.id, EmailDelivery.recipient_id == user.id
                    )
                )
                if delivery.state != "SENT":
                    targets.append((delivery.id, user.email))
            kind = event.type
            body = f"{kind}: visit {get_settings().public_app_url} to view details."
            if "encrypted_token" in payload:
                route = {
                    "VERIFY_EMAIL": "verify-email",
                    "RESET_PASSWORD": "reset-password",
                    "REVIEWER_INVITE": "accept-reviewer-invitation",
                }[kind]
                body = f"Open {get_settings().public_app_url}/{route}?token={unseal(payload['encrypted_token'])}"
        for delivery_id, email in targets:
            send_email(email, "Scriptora: " + kind.replace("_", " ").title(), body)
            with factory.begin() as db:
                db.get(EmailDelivery, delivery_id).state = "SENT"
        with factory.begin() as db:
            event = db.scalar(
                select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
            )
            if event.lease_until == lease:
                event.state, event.lease_until = "SENT", None
                if "encrypted_token" in event.payload:
                    event.payload = {
                        k: v for k, v in event.payload.items() if k != "encrypted_token"
                    }
    except Exception as error:
        with factory.begin() as db:
            event = db.scalar(
                select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
            )
            if event.lease_until != lease:
                return
            event.last_error = type(error).__name__
            event.state = (
                "FAILED" if event.attempt_count >= get_settings().outbox_max_attempts else "PENDING"
            )
            event.available_at = db_now(db) + timedelta(
                seconds=min(3600, 2**event.attempt_count * 10) + random.randint(0, 10)
            )
            event.lease_until = None
            if event.state == "FAILED" and event.type != "DELIVERY_FAILED":
                emit(
                    db,
                    event.aggregate_id,
                    "DELIVERY_FAILED",
                    admins(db),
                    f"delivery-failed:{event.id}",
                )
