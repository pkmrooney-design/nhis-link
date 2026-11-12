import os
import sys
from pathlib import Path

os.environ["ADMIN_PASSWORD"] = "test-pw"
os.environ["SECRET_KEY"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.configure(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    yield
    db.engine.dispose()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/admin/login", json={"password": "test-pw"})
    assert r.status_code == 200
    page = client.get("/admin").text
    csrf = page.split("window.CSRF = ")[1].split(";")[0].strip('"')
    client.headers["X-CSRF-Token"] = csrf
    return client
