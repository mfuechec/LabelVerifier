"""Tests for batch graceful skip of unparseable COLA PDFs."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from app.services.pdf_parser import COLAParseResult
from app.models.schemas import ApplicationData

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cola_pdfs"


def _make_parse_result(brand_name="TEST BRAND", has_images=True):
    """Create a COLAParseResult with optional images."""
    app_data = ApplicationData(
        brand_name=brand_name,
        class_type="VODKA",
        alcohol_content="40",
        net_contents="750 MILLILITERS",
        beverage_type="distilled_spirits",
    )
    images = [("front", b"fake-image-bytes", "image/png")] if has_images else []
    return COLAParseResult(application_data=app_data, label_images=images)


class TestBatchSkipUnparseable:
    """Batch endpoint should skip unparseable PDFs and process valid ones."""

    def test_mix_of_valid_and_invalid_pdfs(self, client):
        """Valid PDFs processed, invalid ones skipped with reason."""
        good_result = _make_parse_result("GOOD BRAND", has_images=True)
        bad_result = _make_parse_result("BAD BRAND", has_images=False)

        # Parser returns good result for first PDF, bad (no images) for second
        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            mock_parser.parse.side_effect = [good_result, bad_result]

            with patch(
                "app.api.routes.batch._process_batch", new_callable=AsyncMock
            ):
                resp = client.post(
                    "/api/v1/batch",
                    files=[
                        ("cola_pdfs[]", ("good.pdf", b"%PDF-valid", "application/pdf")),
                        ("cola_pdfs[]", ("bad.pdf", b"%PDF-nolabels", "application/pdf")),
                    ],
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_items"] == 1
        assert data["skipped_count"] == 1

    def test_all_pdfs_invalid_returns_422(self, client):
        """If every PDF is unparseable, return 422."""
        bad_result = _make_parse_result("BAD", has_images=False)

        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            mock_parser.parse.side_effect = [bad_result, bad_result]

            resp = client.post(
                "/api/v1/batch",
                files=[
                    ("cola_pdfs[]", ("a.pdf", b"%PDF-bad1", "application/pdf")),
                    ("cola_pdfs[]", ("b.pdf", b"%PDF-bad2", "application/pdf")),
                ],
            )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "2" in detail  # mentions count
        assert "skipped" in detail.lower() or "no valid" in detail.lower()

    def test_empty_pdf_is_skipped(self, client):
        """An empty PDF file should be skipped, not crash the batch."""
        good_result = _make_parse_result("GOOD BRAND", has_images=True)

        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            # First call succeeds, empty PDF never reaches parser
            mock_parser.parse.return_value = good_result

            with patch(
                "app.api.routes.batch._process_batch", new_callable=AsyncMock
            ):
                resp = client.post(
                    "/api/v1/batch",
                    files=[
                        ("cola_pdfs[]", ("good.pdf", b"%PDF-valid", "application/pdf")),
                        ("cola_pdfs[]", ("empty.pdf", b"", "application/pdf")),
                    ],
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_items"] == 1
        assert data["skipped_count"] == 1

    def test_non_pdf_content_type_skipped(self, client):
        """Non-PDF content type should be skipped gracefully."""
        good_result = _make_parse_result("GOOD BRAND", has_images=True)

        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            mock_parser.parse.return_value = good_result

            with patch(
                "app.api.routes.batch._process_batch", new_callable=AsyncMock
            ):
                resp = client.post(
                    "/api/v1/batch",
                    files=[
                        ("cola_pdfs[]", ("good.pdf", b"%PDF-valid", "application/pdf")),
                        ("cola_pdfs[]", ("image.png", b"PNG-data", "image/png")),
                    ],
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_items"] == 1
        assert data["skipped_count"] == 1

    def test_parser_valueerror_skipped(self, client):
        """PDF that causes ValueError in parser should be skipped."""
        good_result = _make_parse_result("GOOD BRAND", has_images=True)

        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            mock_parser.parse.side_effect = [good_result, ValueError("Corrupt PDF")]

            with patch(
                "app.api.routes.batch._process_batch", new_callable=AsyncMock
            ):
                resp = client.post(
                    "/api/v1/batch",
                    files=[
                        ("cola_pdfs[]", ("good.pdf", b"%PDF-valid", "application/pdf")),
                        ("cola_pdfs[]", ("corrupt.pdf", b"%PDF-corrupt", "application/pdf")),
                    ],
                )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_items"] == 1
        assert data["skipped_count"] == 1

    def test_get_batch_includes_skipped_items(self, client, db_path):
        """GET /batch/{id} should return skipped_items."""
        good_result = _make_parse_result("GOOD BRAND", has_images=True)
        bad_result = _make_parse_result("BAD BRAND", has_images=False)

        with patch("app.api.routes.batch._pdf_parser") as mock_parser:
            mock_parser.parse.side_effect = [good_result, bad_result]

            with patch(
                "app.api.routes.batch._process_batch", new_callable=AsyncMock
            ):
                resp = client.post(
                    "/api/v1/batch",
                    files=[
                        ("cola_pdfs[]", ("good.pdf", b"%PDF-valid", "application/pdf")),
                        ("cola_pdfs[]", ("bad.pdf", b"%PDF-bad", "application/pdf")),
                    ],
                )

        batch_id = resp.json()["data"]["batch_id"]

        resp2 = client.get(f"/api/v1/batch/{batch_id}")
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert len(data["skipped_items"]) == 1
        assert data["skipped_items"][0]["filename"] == "bad.pdf"
        assert "no label images" in data["skipped_items"][0]["reason"].lower()
