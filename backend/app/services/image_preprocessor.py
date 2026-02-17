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
MIN_DIMENSION = 800

# Target longest side after upscaling small images
TARGET_DIMENSION = 1400

# Anthropic Claude vision processes images up to 1568px on the longest side.
# Images above this are downscaled to avoid wasting tokens on resolution
# the model cannot use.
MAX_DIMENSION = 1568

# JPEG quality for output -- higher preserves small text better
JPEG_QUALITY = 85


def preprocess_image(image_bytes: bytes) -> bytes:
    """Preprocess a label image for better LLM text extraction.

    - Downscales large images to MAX_DIMENSION (Anthropic's internal limit)
    - Upscales small images to TARGET_DIMENSION for text readability
    - Applies mild sharpening to improve text edges
    - Enhances contrast slightly for text readability

    Returns JPEG bytes.
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

    if longest > MAX_DIMENSION:
        # Downscale large images to reduce token count and API latency
        scale = MAX_DIMENSION / longest
        new_w = round(img.size[0] * scale)
        new_h = round(img.size[1] * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info(
            "Downscaled image from %dx%d to %dx%d (%.2fx)",
            original_size[0], original_size[1], new_w, new_h, scale,
        )
    elif longest < MIN_DIMENSION:
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
