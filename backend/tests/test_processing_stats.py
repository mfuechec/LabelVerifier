"""Tests for token/time tracking (LLMCallStats, ProcessingStats) across the pipeline."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.extraction import (
    AnthropicExtractor,
    GroqExtractor,
    ExtractionResult,
    LLMCallStats,
)
from app.models.schemas import ApplicationData, ProcessingStats
from app.services.orchestrator import VerificationOrchestrator
from app.db.setup import create_tables, get_db


VALID_LLM_RESPONSE = json.dumps({
    "brand_name": {"value": "TEST BRAND", "conf": "high"},
    "class_type": {"value": "Vodka", "conf": "high"},
    "alcohol_content": {"value": "40% ABV", "conf": "high"},
    "net_contents": {"value": "750 mL", "conf": "high"},
    "government_warning": {"value": "GOVERNMENT WARNING: (1) test...", "conf": "high"},
    "producer_name": {"value": "TEST PRODUCER", "conf": "high"},
    "producer_address": {"value": None, "conf": "high"},
    "country_of_origin": {"value": None, "conf": "high"},
    "importer_name": {"value": None, "conf": "high"},
    "importer_address": {"value": None, "conf": "high"},
    "sulfites_declaration": {"value": None, "conf": "high"},
    "alcohol_proof": {"value": None, "conf": "high"},
})

WARNING_RESPONSE = json.dumps({
    "government_warning": {"value": "GOVERNMENT WARNING: (1) test...", "conf": "high"},
})

IMPORTER_RESPONSE = json.dumps({
    "importer_name": {"value": None, "conf": "high"},
    "importer_address": {"value": None, "conf": "high"},
})


def _make_anthropic_response(text, input_tokens=100, output_tokens=50):
    """Create a mock Anthropic response with usage stats."""
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


def _make_groq_response(text, prompt_tokens=100, completion_tokens=50):
    """Create a mock Groq response with usage stats."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return resp


class TestLLMCallStats:
    def test_dataclass_creation(self):
        stat = LLMCallStats(input_tokens=100, output_tokens=50, elapsed_ms=200, call_type="extract_fields")
        assert stat.input_tokens == 100
        assert stat.output_tokens == 50
        assert stat.elapsed_ms == 200
        assert stat.call_type == "extract_fields"

    def test_extraction_result_default_empty_stats(self):
        result = ExtractionResult(panel_type="front")
        assert result.llm_stats == []


class TestAnthropicExtractorStats:
    @pytest.mark.asyncio
    async def test_extract_fields_captures_stats(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        mock_resp = _make_anthropic_response(VALID_LLM_RESPONSE, 150, 80)

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert len(result.llm_stats) == 1  # only main extract, no re-extractions
        assert result.llm_stats[0].call_type == "extract_fields"
        assert result.llm_stats[0].input_tokens == 150
        assert result.llm_stats[0].output_tokens == 80
        assert result.llm_stats[0].elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_reextract_warning_captures_stats(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        mock_resp = _make_anthropic_response(WARNING_RESPONSE, 120, 30)

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result, stats = await extractor.reextract_warning(b"fake_image")

        assert stats is not None
        assert stats.call_type == "reextract_warning"
        assert stats.input_tokens == 120
        assert stats.output_tokens == 30

    @pytest.mark.asyncio
    async def test_reextract_specialty_class_captures_stats(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        specialty_resp = json.dumps({
            "fanciful_name": {"value": "Fireball", "conf": "high"},
            "composition_statement": {"value": "Cinnamon Whisky", "conf": "high"},
        })
        mock_resp = _make_anthropic_response(specialty_resp, 130, 40)

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result, stats = await extractor.reextract_specialty_class(b"fake_image")

        assert stats is not None
        assert stats.call_type == "reextract_specialty_class"
        assert stats.input_tokens == 130


class TestGroqExtractorStats:
    @pytest.mark.asyncio
    async def test_extract_fields_captures_stats(self):
        extractor = GroqExtractor(api_key="test-key", model="test-model")

        mock_resp = _make_groq_response(VALID_LLM_RESPONSE, 200, 90)

        with patch.object(
            extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert len(result.llm_stats) == 1
        assert result.llm_stats[0].call_type == "extract_fields"
        assert result.llm_stats[0].input_tokens == 200
        assert result.llm_stats[0].output_tokens == 90
        assert result.llm_stats[0].elapsed_ms >= 0


class TestProcessingStatsModel:
    def test_defaults(self):
        stats = ProcessingStats()
        assert stats.total_llm_calls == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0

    def test_custom_values(self):
        stats = ProcessingStats(
            total_llm_calls=3,
            total_input_tokens=500,
            total_output_tokens=200,
            extraction_time_ms=1500,
            total_time_ms=2000,
        )
        assert stats.total_llm_calls == 3


class TestOrchestratorStats:
    @pytest.fixture
    def orchestrator(self, tmp_db):
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()
        return VerificationOrchestrator(db_path=tmp_db)

    @pytest.mark.asyncio
    async def test_verify_single_returns_processing_stats(self, orchestrator):
        """verify_single should aggregate LLM stats and return ProcessingStats."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            beverage_type="distilled_spirits",
        )

        mock_result = ExtractionResult(
            panel_type="front",
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
            llm_stats=[
                LLMCallStats(input_tokens=150, output_tokens=80, elapsed_ms=500, call_type="extract_fields"),
                LLMCallStats(input_tokens=120, output_tokens=30, elapsed_ms=300, call_type="reextract_warning"),
            ],
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        assert result.processing_stats is not None
        assert result.processing_stats.total_llm_calls == 2
        assert result.processing_stats.total_input_tokens == 270
        assert result.processing_stats.total_output_tokens == 110
        assert result.processing_stats.extraction_time_ms == 800
        assert result.processing_stats.total_time_ms >= 0

    @pytest.mark.asyncio
    async def test_stats_persisted_to_db(self, orchestrator, tmp_db):
        """Processing stats should be persisted to verification_sessions."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )

        mock_result = ExtractionResult(
            panel_type="front",
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
            llm_stats=[
                LLMCallStats(input_tokens=150, output_tokens=80, elapsed_ms=500, call_type="extract_fields"),
            ],
        )

        with patch.object(
            orchestrator.extraction_service,
            "extract_fields",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await orchestrator.verify_single(
                [b"fake_image"], ["front"], app_data
            )

        conn = get_db(tmp_db)
        row = conn.execute(
            "SELECT total_input_tokens, total_output_tokens, total_llm_calls, "
            "processing_time_ms, extraction_time_ms "
            "FROM verification_sessions WHERE id = ?",
            (result.session_id,),
        ).fetchone()
        conn.close()

        assert row["total_input_tokens"] == 150
        assert row["total_output_tokens"] == 80
        assert row["total_llm_calls"] == 1
        assert row["processing_time_ms"] >= 0
        assert row["extraction_time_ms"] == 500


class TestDBMigrationStats:
    def test_migrate_adds_stats_columns(self, tmp_db):
        """Migration should add token/time columns to verification_sessions."""
        import sqlite3
        from app.db.setup import _migrate

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                total_items INTEGER NOT NULL,
                completed_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_sessions (
                id TEXT PRIMARY KEY,
                application_id TEXT,
                beverage_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                overall_confidence REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                brand_name TEXT,
                class_type TEXT
            );
        """)
        conn.commit()

        _migrate(conn)

        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(verification_sessions)").fetchall()
        }
        assert "total_input_tokens" in cols
        assert "total_output_tokens" in cols
        assert "total_llm_calls" in cols
        assert "processing_time_ms" in cols
        assert "extraction_time_ms" in cols
        conn.close()
