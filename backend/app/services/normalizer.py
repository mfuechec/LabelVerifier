import re


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace, remove hyphenated line breaks, trim."""
    if not text:
        return text
    # Remove hyphenation at line breaks (e.g., "BEV-\nERAGES" -> "BEVERAGES")
    text = re.sub(r"-\s*\n\s*", "", text)
    # Replace all whitespace sequences with single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_abv(text: str | None) -> float | None:
    """Extract ABV percentage from various formats."""
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)\s*%", text)
    if match:
        return float(match.group(1))
    return None


def extract_proof(text: str | None) -> float | None:
    """Extract proof value from text."""
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)\s*[Pp]roof", text)
    if match:
        return float(match.group(1))
    return None


def normalize_net_contents(text: str | None) -> tuple[float | None, str | None]:
    """Normalize net contents to a standard value and unit.

    Returns (value_in_ml_or_floz, unit).
    All metric units are converted to mL.
    """
    if not text:
        return (None, None)

    text = text.strip()

    # Try fl oz first
    match = re.search(r"(\d+\.?\d*)\s*fl\.?\s*oz", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)), "fl oz")

    # Try liters (L)
    match = re.search(r"(\d+\.?\d*)\s*L\b", text)
    if match:
        return (float(match.group(1)) * 1000.0, "mL")

    # Try centiliters (cL)
    match = re.search(r"(\d+\.?\d*)\s*cL", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)) * 10.0, "mL")

    # Try milliliters (mL, ML, ml)
    match = re.search(r"(\d+\.?\d*)\s*[Mm][Ll]", text)
    if match:
        return (float(match.group(1)), "mL")

    return (None, None)


def normalize_for_fuzzy(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, strip punctuation, collapse spaces."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
