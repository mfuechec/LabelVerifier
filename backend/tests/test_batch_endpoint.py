import json
import io
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.db.setup import get_db, create_tables
from app.models.schemas import ApplicationData, VerificationResult, ReviewSummary


def _make_app(tmp_db):
    """Create a test FastAPI app with a temp database."""
    from app.main import create_app
    app = create_app()
    app.state.db_path = tmp_db

    conn = get_db(tmp_db)
    create_tables(conn)
    conn.close()
    return app


def _fake_pdf_bytes():
    """Return minimal bytes that pass the empty check."""
    return b"%PDF-1.4 fake pdf content"


def _fake_image_bytes():
    """Return minimal JPEG bytes."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
def app_data():
    return ApplicationData(
        application_id="APP-001",
        brand_name="Test Brand",
        class_type="Bourbon Whiskey",
        alcohol_content="45%",
        net_contents="750 mL",
        beverage_type="distilled_spirits",
    )


@pytest.fixture
def mock_verification_result():
    return VerificationResult(
        session_id="sess-123",
        status="pass",
        overall_confidence=95.0,
        beverage_type="distilled_spirits",
        fields=[],
        annotated_images={},
        created_at="2026-02-15T10:00:00Z",
        review_summary=ReviewSummary(
            total_fields=0,
            fields_needing_review=0,
            fields_reviewed=0,
            flagged_field_names=[],
        ),
    )


class TestBatchPostEndpoint:
    def test_post_batch_returns_batch_id(self, tmp_db, app_data, mock_verification_result):
        app = _make_app(tmp_db)
        client = TestClient(app)

        with patch(
            "app.api.routes.batch._pdf_parser.parse_application_pdf",
            return_value=app_data,
        ), patch(
            "app.api.routes.batch.VerificationOrchestrator",
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.verify_single = AsyncMock(return_value=mock_verification_result)
            mock_orch_cls.return_value = mock_orch

            # Build form data: 1 PDF, 1 image, assignment mapping PDF 0 -> image [0]
            files = [
                ("application_pdfs[]", ("app.pdf", _fake_pdf_bytes(), "application/pdf")),
                ("images[]", ("label.jpg", _fake_image_bytes(), "image/jpeg")),
            ]
            data = {
                "image_assignments[]": json.dumps([0]),
            }

            resp = client.post("/api/v1/batch", files=files, data=data)

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "batch_id" in body
        assert body["total_items"] == 1

    def test_post_batch_multiple_pdfs(self, tmp_db, app_data, mock_verification_result):
        app = _make_app(tmp_db)
        client = TestClient(app)

        with patch(
            "app.api.routes.batch._pdf_parser.parse_application_pdf",
            return_value=app_data,
        ), patch(
            "app.api.routes.batch.VerificationOrchestrator",
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.verify_single = AsyncMock(return_value=mock_verification_result)
            mock_orch_cls.return_value = mock_orch

            files = [
                ("application_pdfs[]", ("app1.pdf", _fake_pdf_bytes(), "application/pdf")),
                ("application_pdfs[]", ("app2.pdf", _fake_pdf_bytes(), "application/pdf")),
                ("images[]", ("label1.jpg", _fake_image_bytes(), "image/jpeg")),
                ("images[]", ("label2.jpg", _fake_image_bytes(), "image/jpeg")),
                ("images[]", ("label3.jpg", _fake_image_bytes(), "image/jpeg")),
            ]
            data = {
                "image_assignments[]": [
                    json.dumps([0]),        # PDF 0 -> image 0
                    json.dumps([1, 2]),     # PDF 1 -> images 1, 2
                ],
            }

            resp = client.post("/api/v1/batch", files=files, data=data)

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total_items"] == 2

    def test_post_batch_no_pdfs_returns_422(self, tmp_db):
        app = _make_app(tmp_db)
        client = TestClient(app)

        resp = client.post("/api/v1/batch", files=[], data={})
        assert resp.status_code == 422

    def test_post_batch_mismatched_assignments_returns_422(self, tmp_db, app_data):
        app = _make_app(tmp_db)
        client = TestClient(app)

        with patch(
            "app.api.routes.batch._pdf_parser.parse_application_pdf",
            return_value=app_data,
        ):
            files = [
                ("application_pdfs[]", ("app.pdf", _fake_pdf_bytes(), "application/pdf")),
                ("images[]", ("label.jpg", _fake_image_bytes(), "image/jpeg")),
            ]
            # 2 assignments for 1 PDF
            data = {
                "image_assignments[]": [
                    json.dumps([0]),
                    json.dumps([0]),
                ],
            }

            resp = client.post("/api/v1/batch", files=files, data=data)

        assert resp.status_code == 422


class TestBatchGetEndpoint:
    def test_get_batch_status(self, tmp_db):
        app = _make_app(tmp_db)
        client = TestClient(app)

        # Seed a batch record
        conn = get_db(tmp_db)
        conn.execute(
            """INSERT INTO batches (id, status, total_items, completed_items, failed_items, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("batch-abc", "processing", 3, 1, 0,
             "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/batch/batch-abc")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["batch"]["batch_id"] == "batch-abc"
        assert body["batch"]["status"] == "processing"
        assert body["batch"]["total_items"] == 3
        assert body["batch"]["completed_items"] == 1
        assert isinstance(body["items"], list)

    def test_get_batch_not_found(self, tmp_db):
        app = _make_app(tmp_db)
        client = TestClient(app)

        resp = client.get("/api/v1/batch/nonexistent")
        assert resp.status_code == 404

    def test_get_batch_includes_sessions(self, tmp_db):
        app = _make_app(tmp_db)
        client = TestClient(app)

        conn = get_db(tmp_db)
        conn.execute(
            """INSERT INTO batches (id, status, total_items, completed_items, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("batch-xyz", "completed", 1, 1,
             "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
        )
        conn.execute(
            """INSERT INTO verification_sessions
               (id, beverage_type, status, overall_confidence, batch_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("sess-1", "distilled_spirits", "pass", 95.0, "batch-xyz",
             "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
        )
        conn.execute(
            """INSERT INTO applications (id, session_id, brand_name)
               VALUES (?, ?, ?)""",
            ("app-1", "sess-1", "Test Brand"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/batch/batch-xyz")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["session_id"] == "sess-1"
        assert items[0]["brand_name"] == "Test Brand"
