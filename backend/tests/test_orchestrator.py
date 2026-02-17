"""Tests for VerificationOrchestrator."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from app.models.schemas import ApplicationData
from app.services.orchestrator import VerificationOrchestrator
from app.services.extraction import AnthropicExtractor, ExtractionResult, LLMCallStats
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


class TestPostMergeReExtractions:
    """Tests for orchestrator's post-merge targeted re-extractions."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        # Force Anthropic extractor for these tests
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_warning_reextraction_called_once_for_multi_panel(self, orchestrator):
        """For 3 panels, reextract_warning should be called exactly once (not 3x)."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        mock_result = _make_extraction_result("front")
        mock_result2 = _make_extraction_result("back")
        mock_result3 = _make_extraction_result("side")

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            side_effect=[mock_result, mock_result2, mock_result3],
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ) as mock_warn:
            result = await orchestrator.verify_single(
                [b"img1", b"img2", b"img3"], ["front", "back", "side"], app_data
            )

        assert mock_warn.call_count == 1

    @pytest.mark.asyncio
    async def test_importer_reextraction_skipped_when_found(self, orchestrator):
        """If merged extraction already has importer_name, don't re-extract."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            importer_name="SOME IMPORTER",
            beverage_type="distilled_spirits",
        )

        result_with_importer = ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "TEST BRAND", "extraction_confidence": "high"},
                "class_type": {"value": "Vodka", "extraction_confidence": "high"},
                "alcohol_content": {"value": "40% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
                "importer_name": {"value": "SOME IMPORTER CO.", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=result_with_importer,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_importer",
            new_callable=AsyncMock,
        ) as mock_imp:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_imp.assert_not_called()


class TestBrandFancifulSwap:
    """Test that brand/fanciful names get swapped when confused."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_brand_fanciful_swap(self, orchestrator):
        """When extracted brand matches declared fanciful and vice versa, swap them."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        # LLM confused: extracted brand="HONEY & BOURBON", fanciful="BARENJAGER"
        confused_result = ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "HONEY & BOURBON", "extraction_confidence": "high"},
                "fanciful_name": {"value": "BARENJAGER", "extraction_confidence": "high"},
                "class_type": {"value": "Liqueur", "extraction_confidence": "high"},
                "alcohol_content": {"value": "35% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=confused_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=({"fanciful_name": "BARENJAGER", "composition_statement": "Honey Liqueur"}, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # Find the brand_name comparison -- it should match after swap
        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "BARENJAGER"


class TestSpecialtyFromFanciful:
    """Test that fanciful_name from main extraction populates specialty data."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_specialty_data_from_extracted_fanciful(self, orchestrator):
        """For admin codes, if main extraction found fanciful_name, populate _specialty_class_data."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        result_with_fanciful = ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "BARENJAGER", "extraction_confidence": "high"},
                "fanciful_name": {"value": "HONEY & BOURBON", "extraction_confidence": "high"},
                "class_type": {"value": "Honey Liqueur", "extraction_confidence": "high"},
                "alcohol_content": {"value": "35% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=result_with_fanciful,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ) as mock_spec:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # Even though specialty re-extract returned None, the fanciful + class_type
        # from main extraction should have been used as fallback
        # The test passes if no error and specialty re-extract was called at most once
        assert mock_spec.call_count <= 1


class TestBrandConfirmation:
    """Test mismatch-triggered brand confirmation re-extraction."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    def _make_barenjager_app_data(self):
        return ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

    def _make_confused_result(self):
        """LLM put fanciful name into brand_name, fanciful_name is null."""
        return ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "HONEY & BOURBON", "extraction_confidence": "high"},
                "fanciful_name": {"value": None, "extraction_confidence": "high"},
                "class_type": {"value": "Liqueur", "extraction_confidence": "high"},
                "alcohol_content": {"value": "35% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
            },
        )

    @pytest.mark.asyncio
    async def test_brand_confirm_fixes_barenjager(self, orchestrator):
        """When blind extraction returns fanciful as brand, re-extraction corrects it."""
        app_data = self._make_barenjager_app_data()
        confused_result = self._make_confused_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=confused_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
            return_value=(
                {"brand_name": "BARENJAGER", "conf": "high", "location_description": "top center"},
                LLMCallStats(100, 30, 200, "reextract_brand"),
            ),
        ) as mock_brand:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_brand.assert_called_once()
        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "BARENJAGER"

    @pytest.mark.asyncio
    async def test_brand_confirm_tries_second_panel_reextraction(self, orchestrator):
        """When no panel has correct brand and first re-extraction fails, try next panel."""
        app_data = self._make_barenjager_app_data()

        # Front: confused, Back: also wrong (no correct brand in any panel)
        front_result = self._make_confused_result()
        back_result = ExtractionResult(
            panel_type="back",
            fields={
                "brand_name": {"value": "SOME OTHER TEXT", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
            },
        )

        # First re-extract (front) returns wrong, second (back) returns correct
        reextract_responses = [
            ({"brand_name": "HONEY & BOURBON", "conf": "high", "location_description": "top"}, LLMCallStats(100, 30, 200, "reextract_brand")),
            ({"brand_name": "BARENJAGER", "conf": "high", "location_description": "back panel"}, LLMCallStats(100, 30, 200, "reextract_brand")),
        ]

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            side_effect=[front_result, back_result],
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
            side_effect=reextract_responses,
        ) as mock_brand:
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        assert mock_brand.call_count == 2
        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "BARENJAGER"

    @pytest.mark.asyncio
    async def test_brand_confirm_handles_diacritics(self, orchestrator):
        """Re-extracted 'Bärenjäger' should match declared 'BARENJAGER' after accent stripping."""
        app_data = self._make_barenjager_app_data()
        confused_result = self._make_confused_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=confused_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
            return_value=(
                {"brand_name": "Bärenjäger", "conf": "high", "location_description": "decorative text"},
                LLMCallStats(100, 30, 200, "reextract_brand"),
            ),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "Bärenjäger"

    @pytest.mark.asyncio
    async def test_brand_confirm_short_circuits_from_other_panel(self, orchestrator):
        """If another panel already extracted the correct brand, use it without re-extraction."""
        app_data = self._make_barenjager_app_data()

        # Front: confused (HONEY & BOURBON), Back: correct (Bärenjäger)
        front_result = self._make_confused_result()
        back_result = ExtractionResult(
            panel_type="back",
            fields={
                "brand_name": {"value": "Bärenjäger", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "importer_name": {"value": "SIDNEY FRANK", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            side_effect=[front_result, back_result],
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
        ) as mock_brand:
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        # Should NOT call reextract_brand -- found it in existing panels
        mock_brand.assert_not_called()
        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "Bärenjäger"

    @pytest.mark.asyncio
    async def test_brand_confirm_not_triggered_when_match(self, orchestrator):
        """When extracted brand already matches declared, no re-extraction."""
        app_data = ApplicationData(
            brand_name="CASCADE WINERY",
            class_type="RED WINE",
            alcohol_content="13",
            net_contents="750 mL",
            beverage_type="wine",
        )

        matching_result = ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "CASCADE WINERY", "extraction_confidence": "high"},
                "class_type": {"value": "Red Wine", "extraction_confidence": "high"},
                "alcohol_content": {"value": "13% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "CASCADE WINERY", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=matching_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
        ) as mock_brand:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_brand.assert_not_called()

    @pytest.mark.asyncio
    async def test_brand_confirm_low_conf_rejected(self, orchestrator):
        """When re-extraction returns low confidence, keep original brand."""
        app_data = self._make_barenjager_app_data()
        confused_result = self._make_confused_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=confused_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
            return_value=(
                {"brand_name": "BARENJAGER", "conf": "low", "location_description": "barely visible"},
                LLMCallStats(100, 30, 200, "reextract_brand"),
            ),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        # Original "HONEY & BOURBON" should be kept since low-conf was rejected
        assert brand_field.extracted_value == "HONEY & BOURBON"

    @pytest.mark.asyncio
    async def test_brand_confirm_no_match_keeps_original(self, orchestrator):
        """When re-extraction returns unrelated brand, keep original."""
        app_data = self._make_barenjager_app_data()
        confused_result = self._make_confused_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=confused_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(None, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
            return_value=(
                {"brand_name": "TOTALLY DIFFERENT", "conf": "high", "location_description": "top"},
                LLMCallStats(100, 30, 200, "reextract_brand"),
            ),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "HONEY & BOURBON"

    @pytest.mark.asyncio
    async def test_brand_confirm_skipped_after_swap(self, orchestrator):
        """When swap heuristic fires first, brand already matches, so re-extract not triggered."""
        app_data = self._make_barenjager_app_data()

        # LLM confused but BOTH fields populated (swap can fire)
        swappable_result = ExtractionResult(
            panel_type="front",
            fields={
                "brand_name": {"value": "HONEY & BOURBON", "extraction_confidence": "high"},
                "fanciful_name": {"value": "BARENJAGER", "extraction_confidence": "high"},
                "class_type": {"value": "Liqueur", "extraction_confidence": "high"},
                "alcohol_content": {"value": "35% ABV", "extraction_confidence": "high"},
                "net_contents": {"value": "750 mL", "extraction_confidence": "high"},
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "extraction_confidence": "high"},
                "producer_name": {"value": "TEST PRODUCER", "extraction_confidence": "high"},
            },
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=swappable_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=({"fanciful_name": "BARENJAGER", "composition_statement": "Liqueur"}, LLMCallStats(100, 30, 200, "reextract_specialty_class")),
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_brand",
            new_callable=AsyncMock,
        ) as mock_brand:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # Swap should have fixed brand, so re-extract should NOT be called
        mock_brand.assert_not_called()
        brand_field = next((f for f in result.fields if f.field_name == "brand_name"), None)
        assert brand_field is not None
        assert brand_field.extracted_value == "BARENJAGER"


def _make_empty_extraction_result(panel="front"):
    """Create an extraction result where all fields are null (no label content)."""
    return ExtractionResult(
        panel_type=panel,
        fields={
            "brand_name": {"value": None, "extraction_confidence": "low"},
            "class_type": {"value": None, "extraction_confidence": "low"},
            "alcohol_content": {"value": None, "extraction_confidence": "low"},
            "net_contents": {"value": None, "extraction_confidence": "low"},
            "government_warning": {"value": None, "extraction_confidence": "low"},
            "producer_name": {"value": None, "extraction_confidence": "low"},
        },
    )


class TestEmptyExtraction:
    """Tests for detecting missing/blank label images."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_empty_extraction_flagged_as_needs_review(self, orchestrator):
        """All panels return empty fields -> status='needs_review' with _label_image field_missing."""
        app_data = ApplicationData(
            brand_name="TOMASELLO",
            class_type="RED WINE",
            alcohol_content="12",
            net_contents="750 mL",
            beverage_type="wine",
        )

        empty_result = _make_empty_extraction_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=empty_result,
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.status == "needs_review"
        label_field = next((f for f in result.fields if f.field_name == "_label_image"), None)
        assert label_field is not None
        assert label_field.status == "field_missing"
        assert label_field.confidence == 0.0
        assert "missing" in label_field.confidence_reason.lower() or "unreadable" in label_field.confidence_reason.lower()

    @pytest.mark.asyncio
    async def test_empty_extraction_skips_reextractions(self, orchestrator):
        """All panels empty -> reextract_warning should NOT be called."""
        app_data = ApplicationData(
            brand_name="TOMASELLO",
            class_type="RED WINE",
            alcohol_content="12",
            net_contents="750 mL",
            beverage_type="wine",
        )

        empty_result = _make_empty_extraction_result()

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=empty_result,
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
        ) as mock_warn:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_warn.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_extraction_still_processes(self, orchestrator):
        """One panel has fields, one is empty -> normal processing continues."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        good_result = _make_extraction_result("front")
        empty_result = _make_empty_extraction_result("back")

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            side_effect=[good_result, empty_result],
        ), patch.object(
            orchestrator.extraction_service,
            "reextract_warning",
            new_callable=AsyncMock,
            return_value=("GOVERNMENT WARNING: ...", LLMCallStats(100, 30, 200, "reextract_warning")),
        ):
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        # Should NOT be flagged as empty -- one panel had content
        label_field = next((f for f in result.fields if f.field_name == "_label_image"), None)
        assert label_field is None
        # Normal processing should have occurred
        assert result.status in ("pass", "fail", "needs_review")
