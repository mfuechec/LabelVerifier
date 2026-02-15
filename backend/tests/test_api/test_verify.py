import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.models.schemas import VerificationResult, FieldComparisonResult


@pytest.fixture
def app(tmp_db):
    application = create_app()
    application.state.db_path = tmp_db
    # Initialize DB
    from app.db.setup import get_db, create_tables
    conn = get_db(tmp_db)
    create_tables(conn)
    conn.close()
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def mock_verification_result():
    return VerificationResult(
        session_id="test-uuid-1",
        status="pass",
        overall_confidence=95.0,
        beverage_type="distilled_spirits",
        fields=[
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="Test Brand",
                extracted_value="Test Brand",
                status="match",
                confidence=95.0,
                match_strategy="fuzzy",
            )
        ],
        annotated_images={},
        created_at="2026-02-14T10:00:00Z",
    )


class TestVerifyEndpoint:
    @pytest.mark.asyncio
    async def test_verify_valid_request(self, client, mock_verification_result):
        with patch("app.api.routes.verify.get_orchestrator") as mock_orch:
            mock_instance = AsyncMock()
            mock_instance.verify_single = AsyncMock(
                return_value=mock_verification_result
            )
            mock_orch.return_value = mock_instance

            app_data = {
                "brand_name": "Test Brand",
                "class_type": "Bourbon",
                "alcohol_content": "45%",
                "net_contents": "750 mL",
                "beverage_type": "distilled_spirits",
            }

            response = await client.post(
                "/api/v1/verify",
                data={
                    "application_data": json.dumps(app_data),
                    "panels[]": "front",
                },
                files={"images[]": ("test.jpg", b"fake-image", "image/jpeg")},
            )

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["session_id"] == "test-uuid-1"
            assert data["status"] == "pass"

    @pytest.mark.asyncio
    async def test_verify_missing_images(self, client):
        response = await client.post(
            "/api/v1/verify",
            data={
                "application_data": json.dumps({
                    "brand_name": "Test",
                    "class_type": "Test",
                    "alcohol_content": "5%",
                    "net_contents": "355 mL",
                    "beverage_type": "beer",
                }),
                "panels[]": "front",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_invalid_application_data(self, client):
        response = await client.post(
            "/api/v1/verify",
            data={
                "application_data": "not valid json",
                "panels[]": "front",
            },
            files={"images[]": ("test.jpg", b"fake-image", "image/jpeg")},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_unsupported_mime_type(self, client):
        app_data = {
            "brand_name": "Test",
            "class_type": "Test",
            "alcohol_content": "5%",
            "net_contents": "355 mL",
            "beverage_type": "beer",
        }
        response = await client.post(
            "/api/v1/verify",
            data={
                "application_data": json.dumps(app_data),
                "panels[]": "front",
            },
            files={"images[]": ("test.gif", b"fake-image", "image/gif")},
        )
        assert response.status_code == 422
        assert "Unsupported file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_verify_image_too_large(self, client):
        app_data = {
            "brand_name": "Test",
            "class_type": "Test",
            "alcohol_content": "5%",
            "net_contents": "355 mL",
            "beverage_type": "beer",
        }
        # Create content larger than 10MB
        large_content = b"x" * (10 * 1024 * 1024 + 1)
        response = await client.post(
            "/api/v1/verify",
            data={
                "application_data": json.dumps(app_data),
                "panels[]": "front",
            },
            files={"images[]": ("test.jpg", large_content, "image/jpeg")},
        )
        assert response.status_code == 422
        assert "Image too large" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_verification_valid_id(self, client, tmp_db):
        from app.db.setup import get_db
        conn = get_db(tmp_db)
        conn.execute(
            """INSERT INTO verification_sessions
               (id, beverage_type, status, overall_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("test-uuid-1", "distilled_spirits", "pass", 95.0,
             "2026-02-14T10:00:00Z", "2026-02-14T10:00:00Z"),
        )
        conn.commit()
        conn.close()

        with patch("app.api.routes.verify.get_db_path") as mock_path:
            mock_path.return_value = tmp_db
            response = await client.get("/api/v1/verify/test-uuid-1")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_verification_not_found(self, client):
        with patch("app.api.routes.verify.get_db_path") as mock_path:
            mock_path.return_value = client._transport.app.state.db_path
            response = await client.get("/api/v1/verify/nonexistent-id")
        assert response.status_code == 404
