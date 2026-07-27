"""SQLAlchemy engine and session construction."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.config.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create one process-local engine without logging credentials."""

    database_url = get_settings().database_url.get_secret_value()
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the shared transaction factory."""

    return sessionmaker(bind=get_engine(), expire_on_commit=False)
