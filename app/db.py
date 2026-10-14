"""SQLAlchemy engine/session handling.

Works unchanged on SQLite (default, local file) and Postgres (DATABASE_URL).
Import `Base` from here for models; use `get_db()` inside a request for a
per-request session. Mirrors luna-lotus-portals/app/db.py.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from flask import g
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_engine(database_url: str) -> Engine:
    global _engine, _SessionLocal
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    _engine = create_engine(database_url, pool_pre_ping=True, future=True, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False,
                                 expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not initialised — call db.init_engine() first.")
    return _engine


def new_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialised — call db.init_engine() first.")
    return _SessionLocal()


def get_db() -> Session:
    session = g.get("db_session")
    if session is None:
        session = new_session()
        g.db_session = session
    return session


def close_db(_exc=None) -> None:
    session = g.pop("db_session", None)
    if session is not None:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


def create_all() -> None:
    Base.metadata.create_all(get_engine())
