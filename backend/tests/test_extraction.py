import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.extraction import ExtractionService


@pytest.fixture
def mock_groq_response():
    """Create a mock Groq API response."""
    mock_message = MagicMock()
    mock_message.content = json.dumps({
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

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


class TestExtractionService:
    @pytest.mark.asyncio
    async def test_extract_fields_calls_api(self, mock_groq_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_groq_response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_fields_parses_response(self, mock_groq_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_groq_response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.fields["brand_name"]["value"] == "Test Brand"
            assert result.fields["class_type"]["value"] == "Bourbon Whiskey"
            assert result.panel_type == "front"

    @pytest.mark.asyncio
    async def test_extract_fields_malformed_json(self):
        mock_message = MagicMock()
        mock_message.content = "This is not valid JSON"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            result = await service.extract_fields(b"fake-image-bytes", "front")

            assert result.error is not None
            assert len(result.fields) == 0

    @pytest.mark.asyncio
    async def test_prompt_includes_required_fields(self, mock_groq_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_groq_response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            prompt_text = str(messages)

            assert "brand_name" in prompt_text
            assert "government_warning" in prompt_text
            assert "bounding_box" in prompt_text

    @pytest.mark.asyncio
    async def test_image_sent_as_base64(self, mock_groq_response):
        with patch("app.services.extraction.AsyncGroq") as mock_groq_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_groq_response)
            mock_groq_cls.return_value = mock_client

            service = ExtractionService(api_key="test-key")
            await service.extract_fields(b"fake-image-bytes", "front")

            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
            content = messages[0]["content"]

            # First content block should be the image URL
            image_block = content[0]
            assert image_block["type"] == "image_url"
            assert "base64" in image_block["image_url"]["url"]
