"""Tests for batch endpoint."""

import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path

from app.models.schemas import VerificationResult, FieldComparisonResult, ReviewSummary

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cola_pdfs"


def _mock_verify_result(session_id="batch-sess-1"):
    return VerificationResult(
        session_id=session_id,
        status="pass",
        overall_confidence=95.0,
        beverage_type="distilled_spirits",
        fields=[],
        annotated_images={},
        created_at="2026-01-01T00:00:00Z",
        review_summary=ReviewSummary(
            total_fields=0,
            fields_needing_review=0,
            fields_reviewed=0,
            flagged_field_names=[],
        ),
    )


class TestBatchEndpoint:
    def test_empty_batch(self, client):
        resp = client.post("/api/v1/batch", files=[])
        assert resp.status_code == 422

    def test_batch_with_valid_pdfs(self, client):
        """Submit multiple COLA PDFs as a batch."""
        pdf_path = FIXTURES_DIR / "barenjager_imported.pdf"
        if not pdf_path.exists():
            pytest.skip("Fixture not found")

        with patch(
            "app.api.routes.batch._process_batch", new_callable=AsyncMock
        ) as mock_process:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            resp = client.post(
                "/api/v1/batch",
                files=[
                    ("cola_pdfs[]", ("test1.pdf", pdf_bytes, "application/pdf")),
                    ("cola_pdfs[]", ("test2.pdf", pdf_bytes, "application/pdf")),
                ],
            )

            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["total_items"] == 2
            assert "batch_id" in data

    def test_get_batch_not_found(self, client):
        resp = client.get("/api/v1/batch/nonexistent")
        assert resp.status_code == 404
