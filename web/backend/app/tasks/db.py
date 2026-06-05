"""Sync SQLAlchemy engine for Celery worker tasks (uses psycopg2 driver)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from app.config import get_settings

settings = get_settings()

_engine = create_engine(settings.database_url, pool_pre_ping=True)
_SessionFactory = sessionmaker(_engine, expire_on_commit=False)


@contextmanager
def get_session() -> Session:
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
