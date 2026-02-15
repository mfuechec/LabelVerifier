import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
import groq
from app.services.extraction import ExtractionService, _repair_json, BaseExtractor, GroqExtractor, AnthropicExtractor


def _make_groq_response(content: str):
    """Create a mock Groq API response with given content."""
    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def _make_rate_limit_error(retry_after: str | None = None):
    """Create a groq.RateLimitError for testing."""
    headers = {}
    if retry_after:
        headers["retry-after"] = retry_after
    request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
    response = httpx.Response(429, headers=headers, request=request)
    return groq.RateLimitError(message="rate limit exceeded", response=response, body=None)


@pytest.fixture
def combined_response():
    """Single-call response with all fields + government warning."""
    return _make_groq_response(json.dumps({
        "brand_name": "Test Brand",
        "class_type": "Bourbon Whiskey",
        "alcohol_content": "45% Alc./Vol.",
        "alcohol_proof": "90 Proof",
        "net_contents": "750 mL",
        "producer_name": "Test Distillery",
        "producer_address": "Louisville, KY",
        "country_of_origin": None,
        "importer_name": None,
        "importer_address": None,
        "government_warning": "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
        "sulfites_declaration": None,
    }))


class TestExtractionService:
    @pytest.mark.asyncio
    async def test_extract_fields_makes_one_call(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_extract_fields_parses_response(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.fields["class_type"]["value"] == "Bourbon Whiskey"
            assert result.fields["government_warning"]["value"] is not None
            assert "Surgeon General" in result.fields["government_warning"]["value"]
            assert result.panel_type == "front"
            assert result.error is None

    @pytest.mark.asyncio
    async def test_extract_fields_malformed_json(self):
        bad_response = _make_groq_response("This is not valid JSON at all")
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=bad_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert len(result.fields) == 0

    @pytest.mark.asyncio
    async def test_prompt_includes_required_fields(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            prompt_text = str(messages)

            assert "brand_name" in prompt_text
            assert "government_warning" in prompt_text

    @pytest.mark.asyncio
    async def test_uses_configured_model(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key", model="custom/model-name")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs.get("model") == "custom/model-name"

    @pytest.mark.asyncio
    async def test_default_model(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs.get("model") == "meta-llama/llama-4-maverick-17b-128e-instruct"

    @pytest.mark.asyncio
    async def test_image_sent_as_base64(self, combined_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=combined_response
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            content = messages[0]["content"]

            image_block = content[0]
            assert image_block["type"] == "image_url"
            assert "base64" in image_block["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_api_error_returns_error_result(self):
        """If the API call fails, we get an error result."""
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.error is not None
            assert "API error" in result.error
            assert len(result.fields) == 0


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_then_success(self, combined_response):
        """Rate limit on first call, success on second."""
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[_make_rate_limit_error(), combined_response]
            )
            mock_groq_cls.return_value = mock_client

            with patch("app.services.extraction.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                service = ExtractionService(api_key="test-key")
                result = await service.extract_fields(b"fake-image-bytes", "front")

                assert result.error is None
                assert result.fields["brand_name"]["value"] == "Test Brand"
                assert mock_client.chat.completions.create.call_count == 2
                mock_sleep.assert_called_once()
                # Default backoff: 2s for first retry (2 * 2^0)
                assert mock_sleep.call_args[0][0] == 2.0

    @pytest.mark.asyncio
    async def test_retry_uses_retry_after_header(self, combined_response):
        """Uses retry-after header when available."""
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[_make_rate_limit_error(retry_after="7"), combined_response]
            )
            mock_groq_cls.return_value = mock_client

            with patch("app.services.extraction.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                service = ExtractionService(api_key="test-key")
                result = await service.extract_fields(b"fake-image-bytes", "front")

                assert result.error is None
                mock_sleep.assert_called_once_with(7.0)

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises(self):
        """After MAX_RETRIES+1 rate limit errors, gives up."""
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[_make_rate_limit_error() for _ in range(4)]
            )
            mock_groq_cls.return_value = mock_client

            with patch("app.services.extraction.asyncio.sleep", new_callable=AsyncMock):
                service = ExtractionService(api_key="test-key")
                result = await service.extract_fields(b"fake-image-bytes", "front")

                # Should return error result after exhausting retries
                assert result.error is not None
                assert "rate limit" in result.error.lower()
                # 1 initial + 3 retries = 4 calls
                assert mock_client.chat.completions.create.call_count == 4

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, combined_response):
        """Backoff doubles each retry: 2s, 4s, 8s."""
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[
                    _make_rate_limit_error(),
                    _make_rate_limit_error(),
                    _make_rate_limit_error(),
                    combined_response,
                ]
            )
            mock_groq_cls.return_value = mock_client

            with patch("app.services.extraction.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                service = ExtractionService(api_key="test-key")
                result = await service.extract_fields(b"fake-image-bytes", "front")

                assert result.error is None
                delays = [call[0][0] for call in mock_sleep.call_args_list]
                assert delays == [2.0, 4.0, 8.0]


class TestRepairJson:
    def test_valid_json_passes_through(self):
        result = _repair_json('{"brand_name": "Test"}')
        assert result == {"brand_name": "Test"}

    def test_strips_markdown_fences(self):
        result = _repair_json('```json\n{"brand_name": "Test"}\n```')
        assert result == {"brand_name": "Test"}

    def test_repairs_truncated_json_missing_braces(self):
        truncated = '{"brand_name": "Test", "class_type": "Bourbon"'
        result = _repair_json(truncated)
        assert result is not None
        assert result["brand_name"] == "Test"

    def test_repairs_truncated_value(self):
        truncated = '{"brand_name": "Test", "class_type": "Bour'
        result = _repair_json(truncated)
        assert result is not None
        assert result["brand_name"] == "Test"

    def test_repairs_trailing_comma(self):
        truncated = '{"brand_name": "Test", "class_type": "Bourbon",'
        result = _repair_json(truncated)
        assert result is not None
        assert result["brand_name"] == "Test"

    def test_unclosed_code_fence(self):
        text = '```json\n{"brand_name": "Test"}'
        result = _repair_json(text)
        assert result is not None
        assert result["brand_name"] == "Test"

    def test_total_garbage_returns_none(self):
        result = _repair_json("This is not JSON at all")
        assert result is None

    def test_regex_fallback_extracts_fields(self):
        # Badly truncated but has extractable key-value pairs
        text = '{"brand_name": "Test Brand", "class_type": "Bourbon", "alcohol_content'
        result = _repair_json(text)
        assert result is not None
        assert result["brand_name"] == "Test Brand"

    def test_null_values_preserved(self):
        result = _repair_json('{"brand_name": "Test", "importer_name": null}')
        assert result is not None
        assert result["brand_name"] == "Test"
        assert result["importer_name"] is None

    def test_nested_confidence_format(self):
        """Nested {"value": ..., "conf": ...} objects should parse correctly."""
        text = json.dumps({
            "brand_name": {"value": "Test Brand", "conf": "high"},
            "class_type": {"value": "Bourbon", "conf": "medium"},
        })
        result = _repair_json(text)
        assert result is not None
        assert result["brand_name"]["value"] == "Test Brand"
        assert result["brand_name"]["conf"] == "high"

    def test_truncated_nested_confidence_format(self):
        """Truncated nested format should still be repairable."""
        text = '{"brand_name": {"value": "Test Brand", "conf": "high"}, "class_type": {"value": "Bour'
        result = _repair_json(text)
        assert result is not None
        assert result["brand_name"]["value"] == "Test Brand"


class TestConfidenceParsing:
    @pytest.mark.asyncio
    async def test_nested_confidence_format_parsed(self):
        """New nested format should populate extraction_confidence."""
        response = _make_groq_response(json.dumps({
            "brand_name": {"value": "Test Brand", "conf": "high"},
            "class_type": {"value": "Bourbon", "conf": "medium"},
            "government_warning": {"value": "GOVERNMENT WARNING: ...", "conf": "low"},
        }))
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.fields["brand_name"]["extraction_confidence"] == "high"
            assert result.fields["class_type"]["extraction_confidence"] == "medium"
            assert result.fields["government_warning"]["extraction_confidence"] == "low"

    @pytest.mark.asyncio
    async def test_flat_format_backward_compat(self):
        """Legacy flat format should default to 'high' confidence."""
        response = _make_groq_response(json.dumps({
            "brand_name": "Test Brand",
            "class_type": "Bourbon",
        }))
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.fields["brand_name"]["extraction_confidence"] == "high"

    @pytest.mark.asyncio
    async def test_prompt_requests_confidence(self):
        """Extraction prompt should request conf field."""
        response = _make_groq_response(json.dumps({
            "brand_name": {"value": "Test", "conf": "high"},
        }))
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            prompt_text = str(messages)
            assert "conf" in prompt_text


class TestBaseExtractor:
    def test_cannot_instantiate_directly(self):
        """BaseExtractor is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseExtractor()


class TestGroqExtractorIsBaseExtractor:
    def test_is_subclass(self):
        """GroqExtractor should be a subclass of BaseExtractor."""
        assert issubclass(GroqExtractor, BaseExtractor)

    def test_instance_is_base_extractor(self):
        """A GroqExtractor instance should be an instance of BaseExtractor."""
        with patch("app.services.extraction.AsyncGroq"):
            extractor = GroqExtractor(api_key="test-key")
            assert isinstance(extractor, BaseExtractor)


class TestAnthropicExtractorIsBaseExtractor:
    def test_is_subclass(self):
        """AnthropicExtractor should be a subclass of BaseExtractor."""
        assert issubclass(AnthropicExtractor, BaseExtractor)

    def test_instance_is_base_extractor(self):
        """An AnthropicExtractor instance should be an instance of BaseExtractor."""
        with patch("app.services.extraction.AsyncAnthropic"):
            extractor = AnthropicExtractor(api_key="test-key")
            assert isinstance(extractor, BaseExtractor)

    @pytest.mark.asyncio
    async def test_extract_fields_calls_anthropic_api(self):
        """AnthropicExtractor should call the Anthropic messages API."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "brand_name": {"value": "Test Brand", "conf": "high"},
            "class_type": {"value": "Bourbon", "conf": "high"},
        }))]

        with patch("app.services.extraction.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            extractor = AnthropicExtractor(api_key="test-key")
            result = await extractor.extract_fields(b"fake-image-bytes", "front")

            # Called 3 times: initial + warning re-extraction + importer re-extraction
            # (importer_name is null in fixture, so importer re-extraction triggers)
            assert mock_client.messages.create.call_count == 3
            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.error is None

    @pytest.mark.asyncio
    async def test_extract_fields_api_error(self):
        """AnthropicExtractor should return error result on API failure."""
        with patch("app.services.extraction.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
            mock_cls.return_value = mock_client

            extractor = AnthropicExtractor(api_key="test-key")
            result = await extractor.extract_fields(b"fake-image-bytes", "front")

            assert result.error is not None
            assert "API error" in result.error


class TestAnthropicImporterReextraction:
    @pytest.mark.asyncio
    async def test_reextracts_importer_when_missing(self):
        """When importer_name is null, should do a focused re-extraction."""
        initial_response = MagicMock()
        initial_response.content = [MagicMock(text=json.dumps({
            "brand_name": {"value": "Bärenjäger", "conf": "high"},
            "importer_name": {"value": None, "conf": "high"},
            "importer_address": {"value": None, "conf": "high"},
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        warning_response = MagicMock()
        warning_response.content = [MagicMock(text=json.dumps({
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        importer_response = MagicMock()
        importer_response.content = [MagicMock(text=json.dumps({
            "importer_name": {"value": "Sidney Frank Importing Co., Inc.", "conf": "high"},
            "importer_address": {"value": "New Rochelle, NY", "conf": "high"},
        }))]

        with patch("app.services.extraction.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=[initial_response, warning_response, importer_response]
            )
            mock_cls.return_value = mock_client

            extractor = AnthropicExtractor(api_key="test-key")
            result = await extractor.extract_fields(b"fake-image-bytes", "front")

            assert mock_client.messages.create.call_count == 3
            assert result.fields["importer_name"]["value"] == "Sidney Frank Importing Co., Inc."
            assert result.fields["importer_address"]["value"] == "New Rochelle, NY"

    @pytest.mark.asyncio
    async def test_skips_importer_reextraction_when_present(self):
        """When importer_name is already extracted, should NOT re-extract."""
        initial_response = MagicMock()
        initial_response.content = [MagicMock(text=json.dumps({
            "brand_name": {"value": "Test", "conf": "high"},
            "importer_name": {"value": "Already Found Inc.", "conf": "high"},
            "importer_address": {"value": "Boston, MA", "conf": "high"},
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        warning_response = MagicMock()
        warning_response.content = [MagicMock(text=json.dumps({
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        with patch("app.services.extraction.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=[initial_response, warning_response]
            )
            mock_cls.return_value = mock_client

            extractor = AnthropicExtractor(api_key="test-key")
            result = await extractor.extract_fields(b"fake-image-bytes", "front")

            # Only 2 calls: initial + warning re-extraction (no importer re-extraction)
            assert mock_client.messages.create.call_count == 2
            assert result.fields["importer_name"]["value"] == "Already Found Inc."

    @pytest.mark.asyncio
    async def test_importer_reextraction_failure_keeps_null(self):
        """If importer re-extraction fails, fields stay null."""
        initial_response = MagicMock()
        initial_response.content = [MagicMock(text=json.dumps({
            "brand_name": {"value": "Test", "conf": "high"},
            "importer_name": {"value": None, "conf": "high"},
            "importer_address": {"value": None, "conf": "high"},
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        warning_response = MagicMock()
        warning_response.content = [MagicMock(text=json.dumps({
            "government_warning": {"value": "GOVERNMENT WARNING: test", "conf": "high"},
        }))]

        with patch("app.services.extraction.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=[initial_response, warning_response, Exception("API error")]
            )
            mock_cls.return_value = mock_client

            extractor = AnthropicExtractor(api_key="test-key")
            result = await extractor.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["importer_name"]["value"] is None


class TestProviderSelection:
    def test_groq_provider_selected(self):
        """Orchestrator should use GroqExtractor when provider is 'groq'."""
        mock_settings = MagicMock()
        mock_settings.llm_provider = "groq"
        mock_settings.groq_api_key = "test-groq-key"
        mock_settings.llm_model = "test-model"
        mock_settings.anthropic_api_key = ""

        with patch("app.services.orchestrator.settings", mock_settings), \
             patch("app.services.extraction.AsyncGroq"):
            from app.services.orchestrator import VerificationOrchestrator
            orch = VerificationOrchestrator()
            assert isinstance(orch.extraction_service, GroqExtractor)

    def test_anthropic_provider_selected(self):
        """Orchestrator should use AnthropicExtractor when provider is 'anthropic'."""
        mock_settings = MagicMock()
        mock_settings.llm_provider = "anthropic"
        mock_settings.anthropic_api_key = "test-anthropic-key"
        mock_settings.llm_model = "claude-haiku-4-5-20251001"
        mock_settings.groq_api_key = ""

        with patch("app.services.orchestrator.settings", mock_settings), \
             patch("app.services.extraction.AsyncAnthropic"):
            from app.services.orchestrator import VerificationOrchestrator
            orch = VerificationOrchestrator()
            assert isinstance(orch.extraction_service, AnthropicExtractor)
