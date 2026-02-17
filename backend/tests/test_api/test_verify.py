"""Tests for POST /verify and GET /verify/{id} endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path

from app.models.schemas import VerificationResult, FieldComparisonResult, ReviewSummary

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cola_pdfs"


def _mock_verify_result(session_id="test-session-123"):
    """Build a minimal VerificationResult for mocking."""
    return VerificationResult(
        session_id=session_id,
        status="pass",
        overall_confidence=95.0,
        beverage_type="distilled_spirits",
        fields=[
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="TEST",
                extracted_value="TEST",
                status="match",
                confidence=100.0,
                match_strategy="fuzzy",
            ),
        ],
        annotated_images={"front": "/api/v1/images/test/front"},
        created_at="2026-01-01T00:00:00Z",
        review_summary=ReviewSummary(
            total_fields=1,
            fields_needing_review=0,
            fields_reviewed=0,
            flagged_field_names=[],
        ),
    )


class TestPostVerify:
    def test_valid_cola_pdf(self, client):
        """POST /verify with a valid COLA PDF should return verification result."""
        pdf_path = FIXTURES_DIR / "barenjager_imported.pdf"
        if not pdf_path.exists():
            pytest.skip("Fixture not found")

        with patch(
            "app.api.routes.verify.get_orchestrator"
        ) as mock_get_orch:
            mock_orch = AsyncMock()
            mock_orch.verify_from_cola.return_value = _mock_verify_result()
            mock_get_orch.return_value = mock_orch

            with open(pdf_path, "rb") as f:
                resp = client.post(
                    "/api/v1/verify",
                    files={"cola_pdf": ("test.pdf", f, "application/pdf")},
                )

            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "pass"
            assert data["session_id"] == "test-session-123"

    def test_empty_pdf(self, client):
        resp = client.post(
            "/api/v1/verify",
            files={"cola_pdf": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 422

    def test_non_pdf_file(self, client):
        resp = client.post(
            "/api/v1/verify",
            files={"cola_pdf": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 422

    def test_invalid_pdf(self, client):
        resp = client.post(
            "/api/v1/verify",
            files={"cola_pdf": ("bad.pdf", b"not valid pdf content", "application/pdf")},
        )
        assert resp.status_code == 422

    def test_stub_pdf_no_images(self, client):
        """A stub PDF with no label images should return 422."""
        import os
        stub_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "data", "applications", "11038001000727.pdf"
        )
        if not os.path.exists(stub_path):
            pytest.skip("Stub PDF fixture not found")

        with open(stub_path, "rb") as f:
            resp = client.post(
                "/api/v1/verify",
                files={"cola_pdf": ("stub.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 422
        assert "No label images" in resp.json()["detail"]


class TestGetVerification:
    def test_not_found(self, client):
        resp = client.get("/api/v1/verify/nonexistent-id")
        assert resp.status_code == 404

    def test_get_existing_session(self, client, db_path):
        """Create a session in DB and retrieve it."""
        from app.db.setup import get_db

        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO verification_sessions
               (id, beverage_type, status, overall_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("sess-1", "distilled_spirits", "pass", 95.0,
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/verify/sess-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["session_id"] == "sess-1"
        assert data["status"] == "pass"


class TestReviewField:
    def test_review_marks_field(self, client, db_path):
        from app.db.setup import get_db
        import uuid

        conn = get_db(db_path)
        sid = "sess-review"
        conn.execute(
            """INSERT INTO verification_sessions
               (id, beverage_type, status, overall_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, "distilled_spirits", "pass", 95.0,
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO comparison_results
               (id, session_id, field_name, match_strategy, status, confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), sid, "brand_name", "fuzzy", "extraction_uncertain", 50.0),
        )
        conn.commit()
        conn.close()

        resp = client.post(f"/api/v1/verify/{sid}/fields/brand_name/review")
        assert resp.status_code == 200
        assert resp.json()["reviewed"] is True
