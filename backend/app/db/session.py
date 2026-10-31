from functools import lru_cache

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)


def db_now(db: Session):
    return db.scalar(select(func.clock_timestamp()))
