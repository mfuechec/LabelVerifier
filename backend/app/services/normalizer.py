import re
import unicodedata


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace, remove hyphenated line breaks, trim."""
    if not text:
        return text
    # Remove hyphenation at line breaks (e.g., "BEV-\nERAGES" -> "BEVERAGES")
    text = re.sub(r"-\s*\n\s*", "", text)
    # Replace all whitespace sequences with single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_warning_text(text: str) -> str:
    """Extra normalization for government warning: removes OCR hyphenation artifacts.

    Handles mid-word hyphens without newlines (e.g., "ALCO-HOLIC" -> "ALCOHOLIC")
    that OCR produces from line-wrapped label text.
    """
    text = normalize_whitespace(text)
    # Remove hyphens between word characters (OCR line-break artifacts)
    # e.g., "ALCO- HOLIC" -> "ALCOHOLIC", "MACHIN-ERY" -> "MACHINERY"
    text = re.sub(r"(\w)-\s*(\w)", r"\1\2", text)
    # Ensure space after parenthesized numbers: "(1)According" -> "(1) According"
    text = re.sub(r"\((\d+)\)(\w)", r"(\1) \2", text)
    # Ensure space before parenthesized numbers: "defects.(2)" -> "defects. (2)"
    text = re.sub(r"(\S)(\(\d+\))", r"\1 \2", text)
    return text


def extract_abv(text: str | None) -> float | None:
    """Extract ABV percentage from various formats.

    Handles: "40%", "40% ABV", "40 %", and plain numbers like "35"
    (as found in COLA application forms).
    """
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)\s*%", text)
    if match:
        return float(match.group(1))
    # Fallback: plain number (COLA forms store just "35")
    match = re.search(r"^(\d+\.?\d*)$", text.strip())
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

    # Try milliliters (mL, ML, ml) -- before liters to avoid "ml" matching "l"
    match = re.search(r"(\d+\.?\d*)\s*[Mm][Ll]\b", text)
    if match:
        return (float(match.group(1)), "mL")

    # Try centiliters (cL)
    match = re.search(r"(\d+\.?\d*)\s*cL", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)) * 10.0, "mL")

    # Try liters: "L", "Liter", "Liters", "Litre", "Litres"
    match = re.search(r"(\d+\.?\d*)\s*(?:Liters?|Litres?|L)\b", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)) * 1000.0, "mL")

    # Try spelled-out units: "MILLILITERS", "MILLILITER"
    match = re.search(r"(\d+\.?\d*)\s*MILLILITERS?\b", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)), "mL")

    # Try gallons: "5.16 U.S. Gallons", "1 Gallon", "1 GAL"
    match = re.search(r"(\d+\.?\d*)\s*(?:U\.?S\.?\s*)?(?:Gallons?|GAL\.?)\b", text, re.IGNORECASE)
    if match:
        return (float(match.group(1)) * 3785.41, "mL")

    return (None, None)


# Common native-language country names mapped to English equivalents
COUNTRY_ALIASES: dict[str, str] = {
    "italia": "italy",
    "deutschland": "germany",
    "españa": "spain",
    "espana": "spain",
    "france": "france",
    "méxico": "mexico",
    "mexique": "mexico",
    "brasil": "brazil",
    "россия": "russia",
    "日本": "japan",
    "中国": "china",
    "écosse": "scotland",
    "ecosse": "scotland",
    "irlande": "ireland",
    "pays-bas": "netherlands",
    "holland": "netherlands",
    "the netherlands": "netherlands",
    "angleterre": "england",
    "royaume-uni": "united kingdom",
    "états-unis": "united states",
    "etats-unis": "united states",
    "kanada": "canada",
    "australie": "australia",
    "nouvelle-zélande": "new zealand",
    "argentine": "argentina",
    "chili": "chile",
    "afrique du sud": "south africa",
    "suède": "sweden",
    "norvège": "norway",
    "danemark": "denmark",
    "finlande": "finland",
    "pologne": "poland",
    "hongrie": "hungary",
    "autriche": "austria",
    "suisse": "switzerland",
    "portugal": "portugal",
    "grèce": "greece",
    "grece": "greece",
    "turquie": "turkey",
}


def normalize_country(text: str) -> str:
    """Normalize country name to English equivalent if known."""
    if not text:
        return text
    lowered = text.strip().lower()
    return COUNTRY_ALIASES.get(lowered, text)


def normalize_company_name(text: str) -> str:
    """Normalize company name for comparison: expand &, strip legal suffixes."""
    if not text:
        return ""
    # Replace & with 'and' before general normalization
    text = text.replace("&", " and ")
    text = normalize_for_fuzzy(text)
    # Strip common legal suffixes
    text = re.sub(
        r"\b(inc|llc|ltd|co|corp|company|corporation|incorporated|importing)\b",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_for_fuzzy(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, fold diacritics, strip punctuation, collapse spaces."""
    if not text:
        return ""
    text = text.lower()
    # Fold diacritics to ASCII (ä→a, é→e, ü→u, etc.)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
