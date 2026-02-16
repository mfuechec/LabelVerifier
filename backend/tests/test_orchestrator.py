"""Tests for VerificationOrchestrator."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from app.models.schemas import ApplicationData
from app.services.orchestrator import VerificationOrchestrator
from app.services.extraction import ExtractionResult
from app.services.pdf_parser import COLAParseResult, LabelImage
from app.db.setup import create_tables, get_db


def _make_extraction_result(panel="front"):
    """Create a mock extraction result with all fields."""
    return ExtractionResult(
        panel_type=panel,
        fields={
            "brand_name": {"value": "TEST BRAND", "extraction_confidence": "high"},
            "class_type": {"value": "Vodka", "extraction_confidence": "high"},
            "alcohol_content": {"value": "40% ABV", "extraction_confidence": "high"},
            "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
            "government_warning": {
                "value": (
                    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
                    "women should not drink alcoholic beverages during pregnancy "
                    "because of the risk of birth defects. (2) Consumption of "
                    "alcoholic beverages impairs your ability to drive a car or "
                    "operate machinery, and may cause health problems."
                ),
                "extraction_confidence": "high",
            },
            "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
        },
    )


@pytest.fixture
def orchestrator(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)
    conn.close()
    return VerificationOrchestrator(db_path=tmp_db)


class TestVerifyFromCola:
    @pytest.mark.asyncio
    async def test_verify_from_cola_calls_verify_single(self, orchestrator):
        """verify_from_cola delegates to verify_single with correct args."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        images = [LabelImage(b"img1", "front", "Brand (front)")]
        parse_result = COLAParseResult(app_data, images)

        with patch.object(orchestrator, "verify_single", new_callable=AsyncMock) as mock_vs:
            mock_vs.return_value = MagicMock()
            await orchestrator.verify_from_cola(parse_result, batch_id="batch-1")

            mock_vs.assert_called_once()
            args = mock_vs.call_args
            assert args[0][0] == [b"img1"]  # images
            assert args[0][1] == ["front"]  # panels
            assert args[0][2].brand_name == "TEST"
            assert args[1]["batch_id"] == "batch-1"


class TestVerifySingle:
    @pytest.mark.asyncio
    async def test_full_pipeline_match(self, orchestrator):
        """Full pipeline with mocked extractor should produce 'pass' for matching data."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        mock_result = _make_extraction_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.status == "pass"
        assert result.overall_confidence >= 90.0
        assert result.session_id is not None
        assert len(result.fields) > 0

    @pytest.mark.asyncio
    async def test_pipeline_brand_mismatch(self, orchestrator):
        """Mismatch in critical field should produce 'fail'."""
        app_data = ApplicationData(
            brand_name="DIFFERENT BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        mock_result = _make_extraction_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.status == "fail"
        brand = next(f for f in result.fields if f.field_name == "brand_name")
        assert brand.status == "content_mismatch"

    @pytest.mark.asyncio
    async def test_pipeline_persists_to_db(self, orchestrator, tmp_db):
        """Verify results are persisted to the database."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=_make_extraction_result(),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        conn = get_db(tmp_db)
        session = conn.execute(
            "SELECT * FROM verification_sessions WHERE id = ?",
            (result.session_id,)
        ).fetchone()
        assert session is not None
        assert session["status"] == "pass"

        app_row = conn.execute(
            "SELECT * FROM applications WHERE session_id = ?",
            (result.session_id,)
        ).fetchone()
        assert app_row is not None
        assert app_row["brand_name"] == "TEST BRAND"
        conn.close()

    @pytest.mark.asyncio
    async def test_pipeline_persists_new_fields(self, orchestrator, tmp_db):
        """New COLA fields (ttb_id, fanciful_name, source_of_product) are persisted."""
        app_data = ApplicationData(
            ttb_id="11115001000373",
            brand_name="TEST",
            fanciful_name="FANCY NAME",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
            source_of_product="imported",
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=_make_extraction_result(),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        conn = get_db(tmp_db)
        app_row = conn.execute(
            "SELECT * FROM applications WHERE session_id = ?",
            (result.session_id,)
        ).fetchone()
        assert app_row["ttb_id"] == "11115001000373"
        assert app_row["fanciful_name"] == "FANCY NAME"
        assert app_row["source_of_product"] == "imported"
        conn.close()

    @pytest.mark.asyncio
    async def test_extraction_error_handled(self, orchestrator):
        """Extraction failure should be handled gracefully."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API error"),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # Should still produce a result, not crash
        assert result.session_id is not None
        assert result.status == "needs_review"
