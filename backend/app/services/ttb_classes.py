"""TTB-recognized class/type reference data and normalization.

Based on 27 CFR Parts 4 (wine), 5 (spirits), and 7 (malt beverages).
"""

import re

# ---------------------------------------------------------------------------
# TTB Spirit Classes (27 CFR Part 5)
# Key: canonical name -> list of recognized variant spellings/names
# ---------------------------------------------------------------------------
TTB_SPIRIT_CLASSES: dict[str, list[str]] = {
    # Whiskey family
    "whiskey": ["whiskey", "whisky"],
    "bourbon whiskey": ["bourbon whiskey", "bourbon whisky", "bourbon"],
    "straight bourbon whiskey": [
        "straight bourbon whiskey",
        "straight bourbon whisky",
        "kentucky straight bourbon whiskey",
        "kentucky straight bourbon whisky",
        "kentucky bourbon whiskey",
        "kentucky bourbon",
    ],
    "rye whiskey": ["rye whiskey", "rye whisky", "rye"],
    "straight rye whiskey": [
        "straight rye whiskey",
        "straight rye whisky",
    ],
    "corn whiskey": ["corn whiskey", "corn whisky"],
    "wheat whiskey": ["wheat whiskey", "wheat whisky"],
    "malt whiskey": ["malt whiskey", "malt whisky"],
    "blended whiskey": ["blended whiskey", "blended whisky"],
    "tennessee whiskey": ["tennessee whiskey", "tennessee whisky"],
    "scotch whisky": ["scotch whisky", "scotch whiskey", "scotch"],
    "irish whiskey": ["irish whiskey", "irish whisky"],
    "canadian whisky": ["canadian whisky", "canadian whiskey"],
    "flavored whiskey": [
        "flavored whiskey",
        "flavored whisky",
    ],
    # Vodka
    "vodka": ["vodka"],
    "flavored vodka": ["flavored vodka"],
    # Gin
    "gin": ["gin"],
    "dry gin": ["dry gin"],
    "london dry gin": ["london dry gin"],
    # Rum
    "rum": ["rum"],
    "flavored rum": ["flavored rum"],
    # Brandy
    "brandy": ["brandy"],
    "grape brandy": ["grape brandy"],
    "fruit brandy": ["fruit brandy"],
    "cognac": ["cognac"],
    "armagnac": ["armagnac"],
    # Tequila / Mezcal
    "tequila": ["tequila"],
    "mezcal": ["mezcal", "mescal"],
    # Liqueur / Cordial
    "liqueur": ["liqueur", "cordial"],
    # Distilled spirits specialty
    "distilled spirits specialty": ["distilled spirits specialty"],
}

# ---------------------------------------------------------------------------
# TTB Wine Classes (27 CFR Part 4)
# ---------------------------------------------------------------------------
TTB_WINE_CLASSES: dict[str, list[str]] = {
    "wine": ["wine"],
    "red wine": ["red wine"],
    "white wine": ["white wine"],
    "rose wine": ["rose wine", "rose", "blush wine"],
    "table wine": ["table wine"],
    "dessert wine": ["dessert wine"],
    "sparkling wine": ["sparkling wine"],
    "champagne": ["champagne"],
    "sherry": ["sherry"],
    "port": ["port", "porto"],
    "vermouth": ["vermouth"],
    "sake": ["sake"],
    "fruit wine": ["fruit wine"],
    "mead": ["mead", "honey wine"],
}

# ---------------------------------------------------------------------------
# TTB Malt Beverage Classes (27 CFR Part 7)
# ---------------------------------------------------------------------------
TTB_BEER_CLASSES: dict[str, list[str]] = {
    "beer": ["beer"],
    "ale": ["ale"],
    "lager": ["lager"],
    "stout": ["stout"],
    "porter": ["porter"],
    "malt beverage": ["malt beverage"],
    "malt liquor": ["malt liquor"],
    "flavored malt beverage": ["flavored malt beverage"],
}

# Map beverage_type to the right class dict
_CLASS_MAPS: dict[str, dict[str, list[str]]] = {
    "distilled_spirits": TTB_SPIRIT_CLASSES,
    "wine": TTB_WINE_CLASSES,
    "malt_beverages": TTB_BEER_CLASSES,
}

# ---------------------------------------------------------------------------
# Qualifier patterns to strip before class matching
# ---------------------------------------------------------------------------
QUALIFIER_PATTERNS: list[re.Pattern] = [
    # Finishing/aging statements
    re.compile(r"\s+finished\s+in\s+.+", re.IGNORECASE),
    re.compile(r"\s+aged\s+in\s+.+", re.IGNORECASE),
    re.compile(r"\s+rested\s+in\s+.+", re.IGNORECASE),
    re.compile(r"\s+barrel\s+rested\b", re.IGNORECASE),
    re.compile(r"\s+cask\s+finished\b", re.IGNORECASE),
    # "infused with ..." (before generic "with")
    re.compile(r"\s+infused\s+with\s+.+", re.IGNORECASE),
    # "with ..." statements
    re.compile(r"\s+with\s+.+", re.IGNORECASE),
    # Geographic/marketing prefixes
    re.compile(r"^locally\s+crafted\s+", re.IGNORECASE),
    re.compile(r"^small\s+batch\s+", re.IGNORECASE),
    re.compile(r"^handcrafted\s+", re.IGNORECASE),
    re.compile(r"^hand\s+crafted\s+", re.IGNORECASE),
    re.compile(r"^craft\s+", re.IGNORECASE),
    re.compile(r"^premium\s+", re.IGNORECASE),
    re.compile(r"^reserve\s+", re.IGNORECASE),
    re.compile(r"^single\s+barrel\s+", re.IGNORECASE),
    # Wine geographic appendages
    re.compile(r"\s+from\s+.+", re.IGNORECASE),
]

# Pattern for flavored spirits: "<flavor> Flavored <base>"
_FLAVORED_PATTERN = re.compile(
    r"^(.+?)\s+flavored\s+(\w+)$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Administrative COLA codes (27 CFR 5.156)
# These are internal TTB category codes that won't appear on physical labels.
# Products with these codes must display a fanciful name + statement of
# composition instead.  Value is the expected base spirit (or None).
# ---------------------------------------------------------------------------
ADMINISTRATIVE_CLASS_TYPES: dict[str, str | None] = {
    "specialties & proprietaries": None,
    "whisky specialties": "whisky",
    "gin specialties": "gin",
    "vodka specialties": "vodka",
    "rum specialties": "rum",
    "other specialties & proprietaries": None,
    "whisky proprietary": "whisky",
    "malt beverages specialities - flavored": None,
    "malt beverages specialities": None,
}

# Known spirit names for pattern-based fallback detection
_KNOWN_SPIRITS = {
    "whisky", "whiskey", "gin", "vodka", "rum", "brandy",
    "tequila", "mezcal", "cognac", "armagnac",
}

# Patterns that indicate an administrative COLA code
_ADMIN_PATTERNS: list[re.Pattern] = [
    # "<spirit> SPECIALTIES" or "<spirit> SPECIALITIES"
    re.compile(r"^(\w+)\s+specialt?ies$", re.IGNORECASE),
    # "<spirit> PROPRIETARY"
    re.compile(r"^(\w+)\s+proprietary$", re.IGNORECASE),
    # "OTHER ... SPECIALTIES & PROPRIETARIES" variants
    re.compile(r"^other\s+.*specialt?ies\b", re.IGNORECASE),
    # "MALT BEVERAGES SPECIALITIES" variants
    re.compile(r"^malt\s+beverages?\s+specialt?ies\b", re.IGNORECASE),
]


def is_administrative_class_type(raw: str | None) -> tuple[bool, str | None]:
    """Check if a class/type string is an administrative COLA code.

    Args:
        raw: The raw class/type string from COLA application data.

    Returns:
        (is_admin, expected_base_spirit) where:
        - is_admin is True if this is an administrative code
        - expected_base_spirit is the base spirit (e.g. "whisky") or None
    """
    if not raw or not raw.strip():
        return (False, None)

    normalized = re.sub(r"\s+", " ", raw.strip()).lower()

    # 1. Exact match against known codes
    if normalized in ADMINISTRATIVE_CLASS_TYPES:
        return (True, ADMINISTRATIVE_CLASS_TYPES[normalized])

    # 2. Pattern-based fallback for unlisted codes
    for pattern in _ADMIN_PATTERNS:
        m = pattern.match(normalized)
        if m:
            # Extract the spirit name from group 1 if it exists
            if m.lastindex and m.lastindex >= 1:
                spirit = m.group(1).lower()
                if spirit in _KNOWN_SPIRITS:
                    return (True, spirit)
            else:
                # Pattern matched but no spirit capture group (e.g. "other..." or "malt...")
                return (True, None)

    return (False, None)


def _build_variant_lookup(
    class_map: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """Build a flat list of (variant_lower, canonical) sorted longest-first."""
    pairs = []
    for canonical, variants in class_map.items():
        for v in variants:
            pairs.append((v.lower(), canonical))
    # Sort by variant length descending so longest match wins
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


# Pre-build lookups
_LOOKUPS: dict[str, list[tuple[str, str]]] = {
    btype: _build_variant_lookup(cmap) for btype, cmap in _CLASS_MAPS.items()
}


def _strip_qualifiers(text: str) -> tuple[str, list[str]]:
    """Strip qualifier patterns from text. Returns (stripped_text, list_of_qualifiers)."""
    qualifiers = []
    current = text
    for pattern in QUALIFIER_PATTERNS:
        match = pattern.search(current)
        if match:
            qualifiers.append(match.group(0).strip())
            current = pattern.sub("", current).strip()
    return current, qualifiers


def _match_class(text_lower: str, beverage_type: str) -> str | None:
    """Try to match text against known TTB classes. Returns canonical name or None."""
    lookup = _LOOKUPS.get(beverage_type, [])
    for variant, canonical in lookup:
        if text_lower == variant:
            return canonical
    return None


def _match_flavored(text_lower: str, beverage_type: str) -> str | None:
    """Handle '<Flavor> Flavored <Base>' pattern -> 'flavored <base>'."""
    m = _FLAVORED_PATTERN.match(text_lower)
    if not m:
        return None
    base = m.group(2).lower()
    # Look up "flavored <base>" in the class map
    flavored_key = f"flavored {base}"
    lookup = _LOOKUPS.get(beverage_type, [])
    for variant, canonical in lookup:
        if variant == flavored_key:
            return canonical
    return None


def normalize_class_type(
    raw: str | None, beverage_type: str
) -> tuple[str | None, str | None]:
    """Normalize a class/type string against TTB-recognized designations.

    Args:
        raw: The raw class/type string (from label or application).
        beverage_type: One of "distilled_spirits", "wine", "malt_beverages".

    Returns:
        (canonical_class, qualifier_text) where:
        - canonical_class is the TTB canonical name, or None if unrecognized
        - qualifier_text is any stripped qualifier text, or None
    """
    if not raw or not raw.strip():
        return (None, None)

    text = re.sub(r"\s+", " ", raw.strip())

    # 1. Try direct match first (before stripping qualifiers)
    text_lower = text.lower()
    # Normalize whisky -> whiskey for matching
    text_lower_norm = text_lower.replace("whisky", "whiskey")

    canonical = _match_class(text_lower_norm, beverage_type)
    if canonical is not None:
        return (canonical, None)

    # 2. Check flavored pattern before stripping
    canonical = _match_flavored(text_lower_norm, beverage_type)
    if canonical is not None:
        return (canonical, None)

    # 3. Strip qualifiers and retry
    stripped, qualifiers = _strip_qualifiers(text)
    stripped_lower = stripped.lower().replace("whisky", "whiskey")

    canonical = _match_class(stripped_lower, beverage_type)
    if canonical is not None:
        qualifier_text = "; ".join(qualifiers) if qualifiers else None
        return (canonical, qualifier_text)

    # 4. Check flavored pattern on stripped text
    canonical = _match_flavored(stripped_lower, beverage_type)
    if canonical is not None:
        qualifier_text = "; ".join(qualifiers) if qualifiers else None
        return (canonical, qualifier_text)

    # 5. Unrecognized
    qualifier_text = "; ".join(qualifiers) if qualifiers else None
    return (None, qualifier_text)
