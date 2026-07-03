from __future__ import annotations

from pathlib import Path

from app.database import create_session_factory, init_db


def test_sqlite_database_directory_is_created(tmp_path: Path):
    database_file = tmp_path / "nested" / "data" / "startup.db"
    engine, _ = create_session_factory(f"sqlite:///{database_file}")
    try:
        init_db(engine)
    finally:
        engine.dispose()

    assert database_file.exists()
