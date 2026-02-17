import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.extraction import ExtractionService


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""
    mock_content = MagicMock()
    mock_content.text = json.dumps({
        "fields": {
            "brand_name": {
                "value": "Test Brand",
                "bounding_box": {"x": 10, "y": 5, "width": 30, "height": 8}
            },
            "class_type": {
                "value": "Bourbon Whiskey",
                "bounding_box": {"x": 10, "y": 15, "width": 30, "height": 6}
            },
            "alcohol_content": {
                "value": "45% Alc./Vol.",
                "bounding_box": {"x": 10, "y": 75, "width": 20, "height": 5}
            },
            "government_warning": {
                "value": None,
                "bounding_box": None
            }
        },
        "extraction_notes": "Clear label, good readability"
    })

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


class TestExtractionService:
    @pytest.mark.asyncio
    async def test_extract_fields_calls_api(self, mock_anthropic_response):
        with patch("app.services.extraction.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_fields_parses_response(self, mock_anthropic_response):
        with patch("app.services.extraction.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.fields["class_type"]["value"] == "Bourbon Whiskey"
            assert result.panel_type == "front"

    @pytest.mark.asyncio
    async def test_extract_fields_malformed_json(self):
        mock_content = MagicMock()
        mock_content.text = "This is not valid JSON"

        mock_response = MagicMock()
        mock_response.content = [mock_content]

        with patch("app.services.extraction.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.error is not None
            assert len(result.fields) == 0

    @pytest.mark.asyncio
    async def test_prompt_includes_required_fields(self, mock_anthropic_response):
        with patch("app.services.extraction.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.messages.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            prompt_text = str(messages)

            assert "brand_name" in prompt_text
            assert "government_warning" in prompt_text
            assert "bounding_box" in prompt_text

    @pytest.mark.asyncio
    async def test_image_sent_as_base64(self, mock_anthropic_response):
        with patch("app.services.extraction.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.messages.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            content = messages[0]["content"]

            # First content block should be the image
            image_block = content[0]
            assert image_block["type"] == "image"
            assert image_block["source"]["type"] == "base64"
