"""Tests for VerificationOrchestrator with transcription-based pipeline."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from app.models.schemas import ApplicationData
from app.services.orchestrator import VerificationOrchestrator
from app.services.extraction import AnthropicExtractor, ExtractionResult, LLMCallStats
from app.services.pdf_parser import COLAParseResult, LabelImage
from app.db.setup import create_tables, get_db


# --- Transcription text fixtures ---

FULL_LABEL_TEXT = (
    "TEST BRAND\n"
    "PREMIUM VODKA\n"
    "ALC. 40% BY VOL.\n"
    "750 mL\n"
    "PRODUCED BY TEST PRODUCER CITY, STATE\n"
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

EMPTY_LABEL_TEXT = ""

BARENJAGER_LABEL_TEXT = (
    "BARENJAGER\n"
    "HONEY & BOURBON\n"
    "HONEY LIQUEUR\n"
    "ALC. 35% BY VOL.\n"
    "750 mL\n"
    "IMPORTED BY SIDNEY FRANK IMPORTING CO., INC.\n"
    "NEW ROCHELLE, N.Y.\n"
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def _mock_transcription(text=FULL_LABEL_TEXT):
    """Create a mock transcription return value."""
    stats = [LLMCallStats(100, 50, 200, "transcribe_label")]
    return (text, stats)


def _patch_transcription(orchestrator, texts=None):
    """Patch transcribe_label to return mock text."""
    if texts is None:
        texts = [FULL_LABEL_TEXT]

    side_effects = [_mock_transcription(t) for t in texts]

    return patch.object(
        orchestrator.extraction_service,
        "transcribe_label",
        new_callable=AsyncMock,
        side_effect=side_effects if len(side_effects) > 1 else None,
        return_value=side_effects[0] if len(side_effects) == 1 else None,
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
    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_full_pipeline_match(self, orchestrator):
        """Full pipeline with mocked transcription should produce 'pass' for matching data."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator):
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

        with _patch_transcription(orchestrator):
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
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator):
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
            brand_name="TEST BRAND",
            fanciful_name="FANCY NAME",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
            source_of_product="imported",
        )

        with _patch_transcription(orchestrator):
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
        """Transcription failure should be handled gracefully."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with patch.object(
            orchestrator.extraction_service,
            "transcribe_label",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API error"),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # Should still produce a result, not crash
        assert result.session_id is not None
        assert result.status == "needs_review"


class TestTranscriptionParallelism:
    """Tests for parallel execution of transcription calls."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_multi_panel_transcriptions_parallel(self, orchestrator):
        """For 2 panels, both transcriptions should run in parallel."""
        import asyncio

        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        call_order = []

        async def mock_transcribe(img, panel, **kwargs):
            call_order.append(f"transcribe_{panel}_start")
            await asyncio.sleep(0.05)
            call_order.append(f"transcribe_{panel}_end")
            return (FULL_LABEL_TEXT, [LLMCallStats(100, 50, 200, "transcribe_label")])

        with patch.object(
            orchestrator.extraction_service, "transcribe_label",
            side_effect=mock_transcribe,
        ):
            await orchestrator.verify_single(
                [b"img1", b"img2"], ["front", "back"], app_data
            )

        starts = [i for i, x in enumerate(call_order) if x.endswith("_start")]
        ends = [i for i, x in enumerate(call_order) if x.endswith("_end")]
        assert len(starts) >= 2, f"Expected at least 2 starts, got: {call_order}"
        assert max(starts) < min(ends), (
            f"Not all tasks started before first finished: {call_order}"
        )


class TestSpecialtyClassHandling:
    """Test admin class type handling with transcription pipeline."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_admin_code_fires_specialty_extraction(self, orchestrator):
        """For admin class codes, specialty extraction fires in parallel with transcription."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [BARENJAGER_LABEL_TEXT]), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(
                {"fanciful_name": "BARENJAGER", "composition_statement": "Honey Liqueur"},
                LLMCallStats(100, 30, 200, "reextract_specialty_class"),
            ),
        ) as mock_spec:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_spec.assert_called_once()
        class_field = next((f for f in result.fields if f.field_name == "class_type"), None)
        assert class_field is not None
        assert class_field.match_strategy == "specialty_class"

    @pytest.mark.asyncio
    async def test_non_admin_skips_specialty_extraction(self, orchestrator):
        """For regular class types, specialty extraction is NOT fired."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
        ) as mock_spec:
            await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_spec.assert_not_called()


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
        """Empty transcription -> status='needs_review' with _label_image field_missing."""
        app_data = ApplicationData(
            brand_name="TOMASELLO",
            class_type="RED WINE",
            alcohol_content="12",
            net_contents="750 mL",
            beverage_type="wine",
        )

        with _patch_transcription(orchestrator, [EMPTY_LABEL_TEXT]):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.status == "needs_review"
        label_field = next((f for f in result.fields if f.field_name == "_label_image"), None)
        assert label_field is not None
        assert label_field.status == "field_missing"
        assert label_field.confidence == 0.0

    @pytest.mark.asyncio
    async def test_partial_extraction_still_processes(self, orchestrator):
        """One panel has text, one is empty -> normal processing continues."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [FULL_LABEL_TEXT, EMPTY_LABEL_TEXT]):
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        # Should NOT be flagged as empty -- one panel had content
        label_field = next((f for f in result.fields if f.field_name == "_label_image"), None)
        assert label_field is None
        assert result.status in ("pass", "fail", "needs_review")


class TestMultiPanelConcatenation:
    """Test that transcriptions from multiple panels are concatenated."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_multi_panel_text_concatenated(self, orchestrator):
        """Brand on front, warning on back -> both found in concatenated text."""
        front_text = "TEST BRAND\nPREMIUM VODKA\nALC. 40% BY VOL.\n750 mL"
        back_text = (
            "PRODUCED BY TEST PRODUCER CITY, STATE\n"
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [front_text, back_text]):
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        brand = next(f for f in result.fields if f.field_name == "brand_name")
        assert brand.status == "match"
        warning = next(f for f in result.fields if f.field_name == "government_warning")
        assert warning.status == "match"


class TestLLMCallReduction:
    """Verify that transcription pipeline uses fewer LLM calls."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_single_panel_one_llm_call(self, orchestrator):
        """Single panel without admin code should use exactly 1 LLM call."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator) as mock_transcribe:
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        mock_transcribe.assert_called_once()
        assert result.processing_stats.total_llm_calls == 1

    @pytest.mark.asyncio
    async def test_matched_text_search_fields_not_flagged_by_compliance(self, orchestrator):
        """Fix 1: Matched text-search fields with None extracted_value should not
        be flagged as missing by compliance checker."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # All fields should be match -- no compliance issues for fields that matched
        compliance_field_names = [i.field_name for i in result.compliance_issues]
        # brand_name, class_type, producer_name are text_search fields that return
        # None as extracted_value but should NOT be flagged as missing
        assert "brand_name" not in compliance_field_names
        assert "class_type" not in compliance_field_names
        assert "producer_name" not in compliance_field_names

    @pytest.mark.asyncio
    async def test_imported_without_country_no_false_fail(self, orchestrator):
        """Fix 5: When COLA doesn't declare country_of_origin, don't flag it."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            class_type="VODKA",
            alcohol_content="35",
            net_contents="750 mL",
            importer_name="SIDNEY FRANK IMPORTING CO.",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [BARENJAGER_LABEL_TEXT]):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        # country_of_origin should NOT appear as a compliance issue
        compliance_field_names = [i.field_name for i in result.compliance_issues]
        assert "country_of_origin" not in compliance_field_names

    @pytest.mark.asyncio
    async def test_admin_code_two_llm_calls(self, orchestrator):
        """Admin code with single panel should use 2 LLM calls (transcribe + specialty)."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [BARENJAGER_LABEL_TEXT]), patch.object(
            orchestrator.extraction_service,
            "reextract_specialty_class",
            new_callable=AsyncMock,
            return_value=(
                {"fanciful_name": "BARENJAGER", "composition_statement": "Honey Liqueur"},
                LLMCallStats(100, 30, 200, "reextract_specialty_class"),
            ),
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.processing_stats.total_llm_calls == 2


class TestAbvReextraction:
    """Test ABV re-extraction on mismatch in orchestrator pipeline."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_abv_reextraction_on_mismatch(self, orchestrator):
        """When initial transcription has wrong ABV, re-extraction should fix it."""
        # Label text has 33% (misread), declared is 35%
        wrong_abv_text = (
            "BARENJAGER\n"
            "HONEY & BOURBON\n"
            "HONEY LIQUEUR\n"
            "ALC. 33% BY VOL.\n"  # Wrong — misread
            "50 mL\n"
            "IMPORTED BY SIDNEY FRANK IMPORTING CO., INC.\n"
            "NEW ROCHELLE, N.Y.\n"
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="HONEY LIQUEUR",
            alcohol_content="35",
            net_contents="50 ML",
            importer_name="SIDNEY FRANK IMPORTING CO., INC.",
            importer_address="NEW ROCHELLE, N.Y.",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [wrong_abv_text]), patch.object(
            orchestrator.extraction_service,
            "reextract_abv",
            new_callable=AsyncMock,
            return_value=("35", LLMCallStats(50, 10, 100, "reextract_abv")),
        ) as mock_reextract:
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        mock_reextract.assert_called_once()
        abv_field = next(f for f in result.fields if f.field_name == "alcohol_content")
        assert abv_field.status == "match"
        assert "re-extraction" in abv_field.confidence_reason.lower()


class TestNetContentsReextraction:
    """Test net contents re-extraction on mismatch in orchestrator pipeline."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        orch = VerificationOrchestrator(db_path=tmp_db)
        orch.extraction_service = AnthropicExtractor(api_key="test-key", model="test-model")
        return orch

    @pytest.mark.asyncio
    async def test_net_contents_reextraction_on_mismatch(self, orchestrator):
        """When initial transcription has wrong net contents, re-extraction should fix it."""
        # Label text has 75 ML (misread of 750), declared is 750 ML
        wrong_nc_text = (
            "HANAMI\n"
            "GIN\n"
            "ALC. 43% BY VOL.\n"
            "75 ML\n"  # Wrong — misread of 750
            "IMPORTED BY THE RED SEA IMPORT COMPANY\n"
            "1607 S 12TH ST, PRINCETON MN 55371\n"
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        app_data = ApplicationData(
            brand_name="HANAMI",
            class_type="GIN",
            alcohol_content="43",
            net_contents="750 MILLILITERS",
            importer_name="THE RED SEA IMPORT COMPANY",
            importer_address="1607 S 12TH ST, PRINCETON MN 55371",
            beverage_type="distilled_spirits",
        )

        with _patch_transcription(orchestrator, [wrong_nc_text]), patch.object(
            orchestrator.extraction_service,
            "reextract_net_contents",
            new_callable=AsyncMock,
            return_value=("750 mL", LLMCallStats(50, 10, 100, "reextract_net_contents")),
        ) as mock_reextract:
            result = await orchestrator.verify_single(
                [b"front_img", b"back_img"], ["front", "back"], app_data
            )

        mock_reextract.assert_called_once()
        nc_field = next(f for f in result.fields if f.field_name == "net_contents")
        assert nc_field.status == "match"
        assert "re-extraction" in nc_field.confidence_reason.lower()
