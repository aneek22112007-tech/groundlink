"""Engine and session. SQLite runs in WAL mode so the agents and the API can share it."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agents.common.models import Base


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///groundlink.db")


def make_engine(url: str | None = None) -> Engine:
    target = url or database_url()
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {"future": True}
    if target.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
        if target in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(target, connect_args=connect_args, **kwargs)
    if target.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


def make_session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(url), expire_on_commit=False, future=True)


def create_all(url: str | None = None) -> sessionmaker[Session]:
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
