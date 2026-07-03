from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app


@pytest.fixture()
def app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    app = create_app(
        {
            "database_url": f"sqlite:///{database_path}",
            "embedded_worker": False,
            "admin_token": "test-token",
            "knowledge_dir": str(Path("knowledge/seed")),
        }
    )
    return app


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers():
    return {"X-Admin-Token": "test-token"}
