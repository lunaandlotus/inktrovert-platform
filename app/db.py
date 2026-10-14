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


def migrate_schema() -> None:
    """Bring older databases up to date.

    create_all() creates missing tables but never alters existing ones, so
    columns added after a table's first creation need explicit migration.
    Currently handles:
      * team_affiliations gaining status / invited_by_user_id / created_at /
        decided_at (roster invites). Pre-existing rows were all effectively
        accepted, so they are stamped accepted.
      * stories gaining state, story_leads gaining suggested_state, and
        profiles gaining featured_state (state-by-state news). All nullable;
        existing rows stay untagged.
    New tables (profile_links) are handled by create_all().
    """
    from sqlalchemy import inspect, text

    engine = get_engine()
    with engine.begin() as conn:
        cols = {c["name"] for c in inspect(engine).get_columns("team_affiliations")}
        wanted = {
            "status": "ALTER TABLE team_affiliations ADD COLUMN status VARCHAR(20) "
                      "NOT NULL DEFAULT 'pending'",
            "invited_by_user_id": "ALTER TABLE team_affiliations ADD COLUMN "
                                  "invited_by_user_id INTEGER",
            "created_at": "ALTER TABLE team_affiliations ADD COLUMN created_at DATETIME",
            "decided_at": "ALTER TABLE team_affiliations ADD COLUMN decided_at DATETIME",
        }
        missing = [name for name in wanted if name not in cols]
        for name in missing:
            conn.execute(text(wanted[name]))
        if "status" in missing:
            # Rows that predate the invite flow were shown publicly, i.e.
            # accepted. (Fresh rows default to pending via the model.)
            conn.execute(text(
                "UPDATE team_affiliations SET status = 'accepted' "
                "WHERE status = 'pending'"))

        # State-by-state news columns — all nullable, existing rows unaffected.
        for table, column in (("stories", "state"),
                             ("story_leads", "suggested_state"),
                             ("profiles", "featured_state")):
            existing = {c["name"] for c in inspect(engine).get_columns(table)}
            if column not in existing:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(2)"))

        # Podcast series topic tag (tattoo / piercing / both) — nullable;
        # the piercing seed backfills the curated series.
        existing = {c["name"] for c in inspect(engine).get_columns("podcast_series")}
        if "topic" not in existing:
            conn.execute(text(
                "ALTER TABLE podcast_series ADD COLUMN topic VARCHAR(20)"))
