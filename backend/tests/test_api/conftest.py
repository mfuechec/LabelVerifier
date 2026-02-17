import os
os.environ["TESTING"] = "1"

import tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db.setup import create_tables, get_db


@pytest.fixture
def app_with_db():
    """Create a test app with a temporary database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    app = create_app()
    app.state.db_path = db_path

    conn = get_db(db_path)
    create_tables(conn)
    conn.close()

    yield app, db_path

    os.unlink(db_path)


@pytest.fixture
def client(app_with_db):
    app, _ = app_with_db
    return TestClient(app)


@pytest.fixture
def db_path(app_with_db):
    _, path = app_with_db
    return path
