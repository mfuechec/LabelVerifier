"""Image preprocessing to improve LLM text extraction quality.

Small or low-quality label images are upscaled and sharpened before
being sent to the vision model, improving readability of small text
like importer info and government warnings.
"""

import io
import logging

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# Images with longest side below this are upscaled
MIN_DIMENSION = 1500

# Target longest side after upscaling
TARGET_DIMENSION = 2000

# JPEG quality for output
JPEG_QUALITY = 92


def preprocess_image(image_bytes: bytes) -> bytes:
    """Preprocess a label image for better LLM text extraction.

    - Upscales small images to TARGET_DIMENSION (preserving aspect ratio)
    - Applies mild sharpening to improve text edges
    - Enhances contrast slightly for text readability

    Returns JPEG bytes. Passes through large images with only
    sharpening/contrast applied (no resize).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        logger.warning("Could not open image for preprocessing, passing through unchanged")
        return image_bytes

    # Convert to RGB if needed (e.g. RGBA PNGs)
    if img.mode != "RGB":
        img = img.convert("RGB")

    original_size = img.size
    longest = max(img.size)

    if longest < MIN_DIMENSION:
        scale = TARGET_DIMENSION / longest
        new_w = round(img.size[0] * scale)
        new_h = round(img.size[1] * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info(
            "Upscaled image from %dx%d to %dx%d (%.1fx)",
            original_size[0], original_size[1], new_w, new_h, scale,
        )

        # Sharpen after upscaling to restore text edges
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

        # Mild contrast boost
        img = ImageEnhance.Contrast(img).enhance(1.2)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()
