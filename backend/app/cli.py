import argparse
import getpass

from email_validator import validate_email
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import db_now, session_factory
from app.models.taxonomy import Outlet, PublicationType, SettingsVersion, Subject, Template
from app.models.users import User, UserRole


def seed(db):
    db.execute(select(func.pg_advisory_xact_lock(17003)))
    for slug, name in (
        ("science", "Science"),
        ("humanities", "Humanities"),
        ("technology", "Technology"),
    ):
        if not db.scalar(select(Subject).where(Subject.slug == slug)):
            db.add(Subject(slug=slug, name=name))
    for code, name in (("JOURNAL", "Journal Article"), ("NEWSLETTER", "Newsletter Article")):
        kind = db.scalar(select(PublicationType).where(PublicationType.code == code))
        if not kind:
            kind = PublicationType(code=code, name=name)
            db.add(kind)
            db.flush()
        slug = code.lower()
        outlet = db.scalar(select(Outlet).where(Outlet.slug == slug))
        if not outlet:
            outlet = Outlet(type_id=kind.id, name="Scriptora " + name, slug=slug)
            db.add(outlet)
            db.flush()
        if not db.scalar(select(Template).where(Template.outlet_id == outlet.id)):
            db.add(
                Template(
                    outlet_id=outlet.id,
                    version=1,
                    validation_schema={
                        "abstract_required": True,
                        "min_words": 100,
                        "max_words": 20000,
                    },
                    instructions="PDF or DOCX. Follow the reviewer formatting checklist.",
                )
            )
    if not db.scalar(select(SettingsVersion)):
        cfg = get_settings()
        db.add(
            SettingsVersion(
                version=1,
                values={
                    "review_duration_hours": cfg.default_review_duration_hours,
                    "publication_fee_minor": cfg.default_publication_fee_minor,
                    "max_live_assignments": cfg.default_max_live_assignments,
                    "payment_instructions": "",
                },
            )
        )


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-taxonomy")
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    args = parser.parse_args()
    with session_factory().begin() as db:
        if args.command == "seed-taxonomy":
            seed(db)
        else:
            email = validate_email(args.email, check_deliverability=False).normalized.lower()
            db.execute(select(func.pg_advisory_xact_lock(17001)))
            if db.scalar(
                select(User.id).join(UserRole).where(User.active, UserRole.role == "ADMIN")
            ):
                parser.error("Bootstrap refused: an active administrator already exists")
            if db.scalar(select(User.id).where(User.email == email)):
                parser.error("Email already exists")
            password = getpass.getpass("Administrator password (12+ characters): ")
            if password != getpass.getpass("Confirm password: "):
                parser.error("Passwords differ")
            user = User(
                email=email,
                display_name="Administrator",
                password_hash=hash_password(password),
                email_verified_at=db_now(db),
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role="ADMIN"))
    print("Completed")


if __name__ == "__main__":
    main()
