import io
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from app.main import create_app
from app.models.schemas import VerificationResult, FieldComparisonResult


def _make_test_pdf(
    brand_name="Test Brand",
    class_type="Bourbon",
    alcohol_content="45%",
    net_contents="750 mL",
    beverage_type="Distilled Spirits",
) -> bytes:
    """Generate a minimal test application PDF."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, height - 1 * inch, "TTB Label Verification - Application Data")

    y = height - 1.6 * inch
    label_x = 1 * inch
    value_x = 3.2 * inch
    line_height = 0.3 * inch

    fields = [
        ("Application ID", "--"),
        ("Brand Name", brand_name),
        ("Class/Type", class_type),
        ("Alcohol Content", alcohol_content),
        ("Net Contents", net_contents),
        ("Producer Name", "--"),
        ("Producer Address", "--"),
        ("Country of Origin", "--"),
        ("Importer Name", "--"),
        ("Importer Address", "--"),
        ("Beverage Type", beverage_type),
        ("Sulfites Declared", "No"),
    ]

    for label, value in fields:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(label_x, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(value_x, y, value)
        y -= line_height

    c.save()
    return buf.getvalue()


@pytest.fixture
def test_pdf():
    return _make_test_pdf()


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
    async def test_verify_valid_request(self, client, mock_verification_result, test_pdf):
        with patch("app.api.routes.verify.get_orchestrator") as mock_orch:
            mock_instance = AsyncMock()
            mock_instance.verify_single = AsyncMock(
                return_value=mock_verification_result
            )
            mock_orch.return_value = mock_instance

            response = await client.post(
                "/api/v1/verify",
                data={"panels[]": "front"},
                files=[
                    ("application_pdf", ("application.pdf", test_pdf, "application/pdf")),
                    ("images[]", ("test.jpg", b"fake-image", "image/jpeg")),
                ],
            )

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["session_id"] == "test-uuid-1"
            assert data["status"] == "pass"

    @pytest.mark.asyncio
    async def test_verify_missing_images(self, client, test_pdf):
        response = await client.post(
            "/api/v1/verify",
            files=[
                ("application_pdf", ("application.pdf", test_pdf, "application/pdf")),
            ],
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_invalid_pdf(self, client):
        response = await client.post(
            "/api/v1/verify",
            data={"panels[]": "front"},
            files=[
                ("application_pdf", ("application.pdf", b"not a pdf", "application/pdf")),
                ("images[]", ("test.jpg", b"fake-image", "image/jpeg")),
            ],
        )
        assert response.status_code == 422
        assert "Failed to parse PDF" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_verify_unsupported_mime_type(self, client, test_pdf):
        response = await client.post(
            "/api/v1/verify",
            data={"panels[]": "front"},
            files=[
                ("application_pdf", ("application.pdf", test_pdf, "application/pdf")),
                ("images[]", ("test.gif", b"fake-image", "image/gif")),
            ],
        )
        assert response.status_code == 422
        assert "Unsupported file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_verify_image_too_large(self, client, test_pdf):
        large_content = b"x" * (10 * 1024 * 1024 + 1)
        response = await client.post(
            "/api/v1/verify",
            data={"panels[]": "front"},
            files=[
                ("application_pdf", ("application.pdf", test_pdf, "application/pdf")),
                ("images[]", ("test.jpg", large_content, "image/jpeg")),
            ],
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
