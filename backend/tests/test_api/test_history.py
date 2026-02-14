import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.db.setup import get_db, create_tables


@pytest.fixture
def app(tmp_db):
    application = create_app()
    application.state.db_path = tmp_db
    conn = get_db(tmp_db)
    create_tables(conn)
    # Insert test data
    for i in range(5):
        conn.execute(
            """INSERT INTO verification_sessions
               (id, application_id, beverage_type, status, overall_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (f"session-{i}", f"APP-{i}", "distilled_spirits",
             "pass" if i < 3 else "fail", 95.0 - i * 5,
             f"2026-02-14T10:{i:02d}:00Z", f"2026-02-14T10:{i:02d}:00Z"),
        )
    conn.commit()
    conn.close()
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHistoryEndpoint:
    @pytest.mark.asyncio
    async def test_list_verifications(self, client, app):
        with patch("app.api.routes.history.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.get("/api/v1/verifications")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client, app):
        with patch("app.api.routes.history.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.get("/api/v1/verifications?status=pass")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_filter_by_beverage_type(self, client, app):
        with patch("app.api.routes.history.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.get(
                "/api/v1/verifications?beverage_type=distilled_spirits"
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_pagination(self, client, app):
        with patch("app.api.routes.history.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.get("/api/v1/verifications?per_page=2&page=1")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["per_page"] == 2
