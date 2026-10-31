"""Destructive fixtures are restricted to an explicit disposable database."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ALLOWED_DATABASES = {"publishing_test", "scriptora_test"}


@pytest.fixture(scope="session")
def pg_engine():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL required; PostgreSQL integration tests are not SQLite tests")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg" or url.database not in ALLOWED_DATABASES:
        pytest.fail(
            "Refusing destructive fixtures: database must be publishing_test or scriptora_test using psycopg"
        )
    previous = os.environ.get("MIGRATION_DATABASE_URL")
    os.environ["MIGRATION_DATABASE_URL"] = raw
    from app.core.config import get_settings

    get_settings.cache_clear()
    engine = create_engine(raw, pool_pre_ping=True)
    config = Config("alembic.ini")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(config, "head")
    command.downgrade(config, "0004_payments_publications")
    command.upgrade(config, "0004_payments_publications")
    command.upgrade(config, "head")
    yield engine
    engine.dispose()
    if previous is None:
        os.environ.pop("MIGRATION_DATABASE_URL", None)
    else:
        os.environ["MIGRATION_DATABASE_URL"] = previous
    get_settings.cache_clear()


@pytest.fixture
def pg(pg_engine):
    from sqlalchemy.orm import Session

    from app.db.base import Base

    with pg_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE " + ",".join('"' + n + '"' for n in Base.metadata.tables) + " CASCADE")
        )
    with Session(pg_engine, expire_on_commit=False) as db:
        yield db
        db.rollback()
