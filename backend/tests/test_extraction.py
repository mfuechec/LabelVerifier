"""Tests for LLM extraction service with mocked Anthropic API."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.extraction import (
    AnthropicExtractor,
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


class TestAnthropicExtractorSingleCall:
    @pytest.mark.asyncio
    async def test_extract_fields_makes_three_focused_calls(self):
        """extract_fields() delegates to 3 focused calls (identity, regulatory, producer)."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        call_count = 0
        original_response = _make_anthropic_mock(VALID_LLM_RESPONSE)

        async def counting_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_response

        with patch.object(
            extractor.client.messages,
            "create",
            new=counting_create,
        ):
            result = await extractor.extract_fields(b"fake_image", "front")

        assert call_count == 3, f"Expected 3 LLM calls, got {call_count}"
        assert len(result.llm_stats) == 3
        call_types = {s.call_type for s in result.llm_stats}
        assert call_types == {"extract_identity", "extract_regulatory", "extract_producer_origin"}


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


class TestFocusedExtractionMethods:
    @pytest.mark.asyncio
    async def test_extract_identity_returns_fields(self):
        """extract_identity should return identity fields."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "brand_name": {"value": "HOWLING MOON", "conf": "high"},
            "class_type": {"value": "Moonshine", "conf": "high"},
            "alcohol_content": {"value": "50% ABV", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            result = await extractor.extract_identity(b"fake_image", "front")

        assert result.fields["brand_name"]["value"] == "HOWLING MOON"
        assert result.fields["class_type"]["value"] == "Moonshine"
        assert result.llm_stats[0].call_type == "extract_identity"

    @pytest.mark.asyncio
    async def test_extract_regulatory_returns_fields(self):
        """extract_regulatory should return regulatory fields."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "government_warning": {"value": "GOVERNMENT WARNING: ...", "conf": "high"},
            "net_contents": {"value": "750 mL", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            result = await extractor.extract_regulatory(b"fake_image", "front")

        assert result.fields["government_warning"]["value"] == "GOVERNMENT WARNING: ..."
        assert result.fields["net_contents"]["value"] == "750 mL"
        assert result.llm_stats[0].call_type == "extract_regulatory"

    @pytest.mark.asyncio
    async def test_extract_producer_origin_returns_fields(self):
        """extract_producer_origin should return producer/origin fields."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "producer_name": {"value": "TEST PRODUCER", "conf": "high"},
            "country_of_origin": {"value": "Austria", "conf": "high"},
            "importer_name": {"value": "NICHE W. & S.", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            result = await extractor.extract_producer_origin(b"fake_image", "front")

        assert result.fields["producer_name"]["value"] == "TEST PRODUCER"
        assert result.fields["country_of_origin"]["value"] == "Austria"
        assert result.llm_stats[0].call_type == "extract_producer_origin"

    @pytest.mark.asyncio
    async def test_focused_extraction_uses_haiku_model(self):
        """Focused extraction methods should use reextract_model (Haiku)."""
        extractor = AnthropicExtractor(
            api_key="test-key", model="claude-sonnet-4-5-20250929",
            reextract_model="claude-haiku-4-5-20251001",
        )

        llm_response = json.dumps({
            "brand_name": {"value": "TEST", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.extract_identity(b"fake_image", "front")

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_focused_extraction_api_error(self):
        """API exception should return ExtractionResult with error."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result = await extractor.extract_identity(b"fake_image", "front")

        assert result.error is not None
        assert "API unavailable" in result.error


class TestMaxTokensPerCallType:
    @pytest.mark.asyncio
    async def test_identity_uses_300_max_tokens(self):
        """extract_identity should use max_tokens=300."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "brand_name": {"value": "TEST", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.extract_identity(b"fake_image", "front")

        assert mock_create.call_args[1]["max_tokens"] == 300

    @pytest.mark.asyncio
    async def test_regulatory_uses_512_max_tokens(self):
        """extract_regulatory should use max_tokens=512."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "government_warning": {"value": "GOVERNMENT WARNING: ...", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.extract_regulatory(b"fake_image", "front")

        assert mock_create.call_args[1]["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_producer_origin_uses_512_max_tokens(self):
        """extract_producer_origin should use max_tokens=512."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "producer_name": {"value": "TEST", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.extract_producer_origin(b"fake_image", "front")

        assert mock_create.call_args[1]["max_tokens"] == 512


class TestReextractMissingFields:
    @pytest.mark.asyncio
    async def test_reextract_missing_fields_returns_result(self):
        """reextract_missing_fields should return ExtractionResult with requested fields."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "government_warning": {
                "value": "GOVERNMENT WARNING: (1) According to the Surgeon General...",
                "conf": "medium",
            },
            "net_contents": {"value": "750 mL", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            result = await extractor.reextract_missing_fields(
                b"fake_image", ["government_warning", "net_contents"],
            )

        assert isinstance(result, ExtractionResult)
        assert result.fields["government_warning"]["value"] is not None
        assert result.fields["net_contents"]["value"] == "750 mL"
        assert result.llm_stats[0].call_type == "reextract_missing_fields"

    @pytest.mark.asyncio
    async def test_reextract_missing_fields_uses_512_max_tokens(self):
        """reextract_missing_fields should use max_tokens=512."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "producer_name": {"value": "TEST CO", "conf": "high"},
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.reextract_missing_fields(
                b"fake_image", ["producer_name"],
            )

        assert mock_create.call_args[1]["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_reextract_missing_fields_api_error(self):
        """API error should return ExtractionResult with error."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result = await extractor.reextract_missing_fields(
                b"fake_image", ["government_warning"],
            )

        assert result.error is not None


class TestAnthropicRateLimitRetry:
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Anthropic 429 should be retried with backoff."""
        from anthropic import RateLimitError as AnthropicRateLimitError
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "brand_name": {"value": "TEST", "conf": "high"},
        })

        # First call raises rate limit, second succeeds
        mock_error_response = MagicMock()
        mock_error_response.status_code = 429
        mock_error_response.headers = {"retry-after": "0.1"}
        rate_limit_error = AnthropicRateLimitError(
            message="Rate limited",
            response=mock_error_response,
            body={"error": {"type": "rate_limit_error", "message": "Rate limited"}},
        )

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=[rate_limit_error, _make_anthropic_mock(llm_response)],
        ) as mock_create:
            result = await extractor.extract_identity(b"fake_image", "front")

        assert mock_create.call_count == 2
        assert result.error is None
        assert result.fields["brand_name"]["value"] == "TEST"

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_returns_error(self):
        """After all retries exhausted on rate limit, return error result."""
        from anthropic import RateLimitError as AnthropicRateLimitError
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        mock_error_response = MagicMock()
        mock_error_response.status_code = 429
        mock_error_response.headers = {}
        rate_limit_error = AnthropicRateLimitError(
            message="Rate limited",
            response=mock_error_response,
            body={"error": {"type": "rate_limit_error", "message": "Rate limited"}},
        )

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=rate_limit_error,
        ), patch("app.services.extraction.INITIAL_BACKOFF_SECONDS", 0.01):
            result = await extractor.extract_identity(b"fake_image", "front")

        assert result.error is not None
        assert "Rate limited" in result.error


class TestReextractionUsesHaikuByDefault:

    @pytest.mark.asyncio
    async def test_brand_reextract_uses_fast_model(self):
        """reextract_brand should use reextract_model."""
        extractor = AnthropicExtractor(
            api_key="test-key", model="claude-sonnet-4-5-20250929",
            reextract_model="claude-haiku-4-5-20251001",
        )

        llm_response = json.dumps({
            "brand_name": {"value": "TEST", "conf": "high"},
            "location_description": "top",
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ) as mock_create:
            await extractor.reextract_brand(b"fake_image", "TEST")

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


class TestTranscribeLabel:
    @pytest.mark.asyncio
    async def test_transcribe_label_returns_text(self):
        """transcribe_label should return plain text + stats."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        label_text = "BARENJAGER\nHONEY LIQUEUR\n750 mL\n35% ALC./VOL."

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(label_text),
        ):
            text, stats = await extractor.transcribe_label(b"fake_image", "front")

        assert text == label_text
        assert len(stats) == 1
        assert stats[0].call_type == "transcribe_label"

    @pytest.mark.asyncio
    async def test_transcribe_label_uses_4000_max_tokens(self):
        """transcribe_label should use max_tokens=4000 to avoid truncation on dense labels."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock("some text"),
        ) as mock_create:
            await extractor.transcribe_label(b"fake_image", "front")

        assert mock_create.call_args[1]["max_tokens"] == 4000

    @pytest.mark.asyncio
    async def test_transcribe_label_api_error_returns_empty(self):
        """API exception should return empty string."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            text, stats = await extractor.transcribe_label(b"fake_image", "front")

        assert text == ""


class TestBrandReextraction:
    @pytest.mark.asyncio
    async def test_reextract_brand_returns_result(self):
        """reextract_brand should return brand dict + stats on success."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({
            "brand_name": {"value": "BARENJAGER", "conf": "high"},
            "location_description": "large text at top center",
        })

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            result, stats = await extractor.reextract_brand(b"fake_image", "BARENJAGER")

        assert result is not None
        assert result["brand_name"] == "BARENJAGER"
        assert result["conf"] == "high"
        assert result["location_description"] == "large text at top center"
        assert stats is not None
        assert stats.call_type == "reextract_brand"

    @pytest.mark.asyncio
    async def test_reextract_brand_api_error(self):
        """API exception should return (None, None)."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result, stats = await extractor.reextract_brand(b"fake_image", "BARENJAGER")

        assert result is None
        assert stats is None


class TestAbvReextraction:
    @pytest.mark.asyncio
    async def test_reextract_abv_returns_value(self):
        """reextract_abv should return ABV string + stats on success."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({"abv": "35"})

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            abv, stats = await extractor.reextract_abv(b"fake_image")

        assert abv == "35"
        assert stats is not None
        assert stats.call_type == "reextract_abv"

    @pytest.mark.asyncio
    async def test_reextract_abv_handles_error(self):
        """API exception should return (None, None)."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            abv, stats = await extractor.reextract_abv(b"fake_image")

        assert abv is None
        assert stats is None


class TestNetContentsReextraction:
    @pytest.mark.asyncio
    async def test_reextract_net_contents_returns_value(self):
        """reextract_net_contents should return net contents string + stats."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        llm_response = json.dumps({"net_contents": "750 mL"})

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=_make_anthropic_mock(llm_response),
        ):
            nc, stats = await extractor.reextract_net_contents(b"fake_image")

        assert nc == "750 mL"
        assert stats is not None
        assert stats.call_type == "reextract_net_contents"

    @pytest.mark.asyncio
    async def test_reextract_net_contents_handles_error(self):
        """API exception should return (None, None)."""
        extractor = AnthropicExtractor(api_key="test-key", model="test-model")

        with patch.object(
            extractor.client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            nc, stats = await extractor.reextract_net_contents(b"fake_image")

        assert nc is None
        assert stats is None
