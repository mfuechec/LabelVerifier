"""Tests for LLM extraction service (Anthropic + Groq) with mocked APIs."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.extraction import (
    AnthropicExtractor,
    GroqExtractor,
    ExtractionResult,
)


VALID_LLM_RESPONSE = json.dumps({
    "brand_name": {"value": "HOWLING MOON", "conf": "high"},
    "class_type": {"value": "Moonshine", "conf": "high"},
    "alcohol_content": {"value": "50% ABV", "conf": "high"},
    "net_contents": {"value": "750 mL", "conf": "high"},
    "government_warning": {
        "value": "GOVERNMENT WARNING: (1) According to the Surgeon General...",
        "conf": "medium",
    },
    "producer_name": {"value": "Howling Moon LLC", "conf": "high"},
    "producer_address": {"value": "Asheville, NC", "conf": "high"},
    "country_of_origin": {"value": None, "conf": "high"},
    "importer_name": {"value": None, "conf": "high"},
    "importer_address": {"value": None, "conf": "high"},
    "sulfites_declaration": {"value": None, "conf": "high"},
    "alcohol_proof": {"value": "100 Proof", "conf": "high"},
})


def _make_anthropic_mock(text):
    """Create a mock Anthropic response with usage."""
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50)
    return resp


class TestAnthropicExtractor:
    @pytest.mark.asyncio
    async def test_extract_fields_returns_result(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(VALID_LLM_RESPONSE),
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert isinstance(result, ExtractionResult)
        assert result.panel_type == "front"
        assert result.fields["brand_name"]["value"] == "HOWLING MOON"

    @pytest.mark.asyncio
    async def test_extract_handles_markdown_json(self):
        """LLM sometimes wraps JSON in markdown code blocks."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        markdown_response = f"```json\n{VALID_LLM_RESPONSE}\n```"

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(markdown_response),
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert result.fields["brand_name"]["value"] == "HOWLING MOON"

    @pytest.mark.asyncio
    async def test_extraction_confidence_mapping(self):
        """'conf' field should be mapped to 'extraction_confidence'."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(VALID_LLM_RESPONSE),
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert result.fields["government_warning"]["extraction_confidence"] == "medium"
        assert result.fields["brand_name"]["extraction_confidence"] == "high"


class TestGroqExtractor:
    @pytest.mark.asyncio
    async def test_extract_fields_returns_result(self):
        extractor = GroqExtractor(api_key="test-key", model="test-model")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=VALID_LLM_RESPONSE))
        ]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch.object(
            extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert isinstance(result, ExtractionResult)
        assert result.fields["brand_name"]["value"] == "HOWLING MOON"


class TestExtractionErrorHandling:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock("not valid json at all"),
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        # Should either return an error result or have empty fields
        assert result.error or len(result.fields) == 0

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self):
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert result.error is not None
