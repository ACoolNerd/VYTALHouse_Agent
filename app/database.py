from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str):
    if database_url.startswith("sqlite:///"):
        sqlite_target = database_url.removeprefix("sqlite:///")
        if sqlite_target and sqlite_target != ":memory:":
            Path(sqlite_target).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine) -> None:
    Base.metadata.create_all(bind=engine)
