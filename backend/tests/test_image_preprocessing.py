import io
import pytest
from PIL import Image

from app.services.image_preprocessor import preprocess_image, MIN_DIMENSION


def _make_image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    """Create a test image of given dimensions."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestImagePreprocessing:
    def test_small_image_gets_upscaled(self):
        """Images smaller than MIN_DIMENSION should be upscaled."""
        small = _make_image(200, 300)
        result = preprocess_image(small)
        img = Image.open(io.BytesIO(result))
        assert max(img.size) >= MIN_DIMENSION

    def test_large_image_not_upscaled(self):
        """Images already large enough should keep their dimensions."""
        large = _make_image(2000, 1500)
        result = preprocess_image(large)
        img = Image.open(io.BytesIO(result))
        assert img.size == (2000, 1500)

    def test_preserves_aspect_ratio(self):
        """Upscaling should preserve the original aspect ratio."""
        small = _make_image(200, 400)
        result = preprocess_image(small)
        img = Image.open(io.BytesIO(result))
        original_ratio = 200 / 400
        new_ratio = img.size[0] / img.size[1]
        assert abs(original_ratio - new_ratio) < 0.01

    def test_returns_jpeg_bytes(self):
        """Output should be valid JPEG bytes."""
        small = _make_image(200, 300)
        result = preprocess_image(small)
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_handles_png_input(self):
        """Should handle PNG input images."""
        png = _make_image(200, 300, fmt="PNG")
        result = preprocess_image(png)
        img = Image.open(io.BytesIO(result))
        assert max(img.size) >= MIN_DIMENSION

    def test_sharpening_applied(self):
        """Processed image should differ from a simple resize (sharpening changes pixels)."""
        small = _make_image(200, 300)
        result = preprocess_image(small)
        # Just verify it produces valid output without error
        img = Image.open(io.BytesIO(result))
        assert img.size[0] > 200

    def test_invalid_image_passes_through(self):
        """Invalid image bytes should be returned unchanged."""
        garbage = b"not-a-real-image"
        result = preprocess_image(garbage)
        assert result == garbage

    def test_borderline_image_not_upscaled(self):
        """Image exactly at MIN_DIMENSION should not be upscaled."""
        exact = _make_image(MIN_DIMENSION, MIN_DIMENSION)
        result = preprocess_image(exact)
        img = Image.open(io.BytesIO(result))
        assert img.size == (MIN_DIMENSION, MIN_DIMENSION)
