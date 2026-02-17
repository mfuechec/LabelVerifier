"""Tests for image preprocessing."""

import io

from PIL import Image

from app.services.image_preprocessor import (
    MAX_DIMENSION,
    MIN_DIMENSION,
    preprocess_image,
)


def _make_image(width: int, height: int) -> bytes:
    """Create a test JPEG image of given dimensions."""
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _get_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Get (width, height) from image bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    return img.size


class TestDownscaling:
    def test_large_image_downscaled_to_max_dimension(self):
        """Images larger than MAX_DIMENSION should be downscaled."""
        result = preprocess_image(_make_image(3000, 2000))
        w, h = _get_dimensions(result)
        assert max(w, h) <= MAX_DIMENSION

    def test_large_image_preserves_aspect_ratio(self):
        """Downscaling should preserve aspect ratio."""
        result = preprocess_image(_make_image(3000, 1500))
        w, h = _get_dimensions(result)
        assert abs(w / h - 2.0) < 0.05  # 3000:1500 = 2:1

    def test_image_at_max_dimension_not_resized(self):
        """Image exactly at MAX_DIMENSION should not be resized."""
        result = preprocess_image(_make_image(MAX_DIMENSION, 1000))
        w, h = _get_dimensions(result)
        assert w == MAX_DIMENSION


class TestUpscaling:
    def test_small_image_upscaled(self):
        """Images smaller than MIN_DIMENSION should be upscaled."""
        result = preprocess_image(_make_image(500, 400))
        w, h = _get_dimensions(result)
        assert max(w, h) > MIN_DIMENSION

    def test_medium_image_not_resized(self):
        """Images between MIN and MAX should not be resized."""
        result = preprocess_image(_make_image(900, 700))
        w, h = _get_dimensions(result)
        assert w == 900


class TestPassthrough:
    def test_invalid_bytes_passed_through(self):
        """Non-image bytes should be returned unchanged."""
        bad_bytes = b"not an image"
        result = preprocess_image(bad_bytes)
        assert result == bad_bytes
