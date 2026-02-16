from rapidfuzz import fuzz
from app.services.normalizer import (
    normalize_whitespace,
    normalize_warning_text,
    normalize_for_fuzzy,
    normalize_company_name,
    normalize_country,
    extract_abv,
    extract_proof,
    normalize_net_contents,
)
from app.services.ttb_classes import normalize_class_type, is_administrative_class_type
from app.models.schemas import ApplicationData, FieldComparisonResult


CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

FUZZY_THRESHOLD = 85.0


def exact_match(extracted: str, canonical: str) -> tuple[str, float, str]:
    """Case-insensitive exact match after whitespace normalization. Used for government warning."""
    norm_ext = normalize_whitespace(extracted).lower()
    norm_can = normalize_whitespace(canonical).lower()

    if norm_ext == norm_can:
        return ("match", 100.0, "Exact match")

    # Try again with OCR artifact normalization (mid-word hyphens removed)
    clean_ext = normalize_warning_text(extracted).lower()
    clean_can = normalize_warning_text(canonical).lower()

    if clean_ext == clean_can:
        return ("match", 100.0, "Exact match (after OCR normalization)")

    # Calculate similarity for partial credit
    ratio = fuzz.ratio(clean_ext, clean_can)
    return ("content_mismatch", ratio, f"Word-level similarity: {ratio:.0f}%")


_US_STATE_ABBREVS: dict[str, str] = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
}
_STATE_FULL_TO_ABBREV = {**_US_STATE_ABBREVS}
_STATE_ABBREV_TO_FULL = {v: k for k, v in _US_STATE_ABBREVS.items()}


def _normalize_address_tokens(text: str) -> set[str]:
    """Normalize an address string into a set of comparable tokens.

    Expands/collapses state names so 'North Carolina' and 'NC' both yield {'nc'}.
    Strips punctuation, zips, and common noise words.
    """
    import re as _re
    # Collapse dotted abbreviations before fuzzy normalization: "N.Y." -> "NY"
    text = _re.sub(r"\b([A-Za-z])\.([A-Za-z])\.", r"\1\2", text)
    t = normalize_for_fuzzy(text)
    # Remove zip codes
    t = _re.sub(r"\b\d{5}(?:-\d{4})?\b", "", t)
    # Remove street numbers at start (e.g. "42 old elk mountain rd")
    t = _re.sub(r"^\d+\s+", "", t)

    tokens = set(t.split())
    # Remove noise words
    tokens -= {"st", "rd", "ave", "blvd", "dr", "ln", "ct", "ste", "suite", "apt"}

    # Expand full state names to abbreviations for normalization
    for full_name, abbrev in _STATE_FULL_TO_ABBREV.items():
        full_words = set(full_name.split())
        if full_words.issubset(tokens):
            tokens -= full_words
            tokens.add(abbrev)

    return tokens


def address_match(
    extracted: str | None, declared: str
) -> tuple[str, float, str]:
    """Address match: accepts city/state partial matches.

    Labels often print only city/state while applications have full street addresses.
    If all extracted address tokens appear in the declared address, it's a match.
    Falls back to standard fuzzy match otherwise.
    """
    if not extracted:
        return ("field_missing", 0.0, "Field not found on label")

    ext_tokens = _normalize_address_tokens(extracted)
    dec_tokens = _normalize_address_tokens(declared)

    if not ext_tokens:
        return ("field_missing", 0.0, "Field not found on label")

    # If all extracted tokens are found in declared, treat as match
    if ext_tokens.issubset(dec_tokens) and len(ext_tokens) >= 1:
        return ("match", 100.0, f"Address match: extracted location found in declared address")

    # Fall back to standard fuzzy
    return fuzzy_match(extracted, declared)


def fuzzy_match(
    extracted: str | None, declared: str, threshold: float = FUZZY_THRESHOLD
) -> tuple[str, float, str]:
    """Fuzzy match for brand name, producer, address, country, etc."""
    if not extracted:
        return ("field_missing", 0.0, "Field not found on label")

    norm_ext = normalize_for_fuzzy(extracted)
    norm_dec = normalize_for_fuzzy(declared)

    if not norm_ext:
        return ("field_missing", 0.0, "Field not found on label")

    # Check if one value fully contains the other (e.g. "Cascade" in "Cascade Winery")
    # Guard: require either 2+ words or the shorter string being at least 50% of the longer.
    # Prevents single short tokens like "Fete" matching "Lenz Moser Fête Rosé".
    shorter, longer = (norm_dec, norm_ext) if len(norm_dec) <= len(norm_ext) else (norm_ext, norm_dec)
    length_ratio = len(shorter) / len(longer) if longer else 0
    containment_ok = len(shorter.split()) >= 2 or length_ratio >= 0.5
    if (norm_dec in norm_ext or norm_ext in norm_dec) and containment_ok:
        best_ratio = max(fuzz.partial_ratio(norm_ext, norm_dec), fuzz.token_set_ratio(norm_ext, norm_dec))
        if best_ratio >= threshold:
            return ("match", best_ratio, f"Fuzzy match: {best_ratio:.0f}% (containment match, threshold: {threshold:.0f}%)")

    # Blend strict and lenient ratios to prevent short-token inflation
    strict_ratio = max(fuzz.ratio(norm_ext, norm_dec), fuzz.token_sort_ratio(norm_ext, norm_dec))
    lenient_ratio = max(fuzz.token_set_ratio(norm_ext, norm_dec), fuzz.partial_ratio(norm_ext, norm_dec))
    best_ratio = 0.7 * strict_ratio + 0.3 * lenient_ratio

    if best_ratio >= threshold:
        return ("match", best_ratio, f"Fuzzy match: {best_ratio:.0f}% (threshold: {threshold:.0f}%)")
    return ("content_mismatch", best_ratio, f"Fuzzy match: {best_ratio:.0f}% -- below {threshold:.0f}% threshold")


def class_type_match(
    extracted: str | None, declared: str, beverage_type: str
) -> tuple[str, float, str]:
    """TTB-aware class/type comparison with normalization and fuzzy fallback."""
    if not extracted or not extracted.strip():
        return ("field_missing", 0.0, "Class/type not found on label")

    ext_canonical, ext_qualifier = normalize_class_type(extracted, beverage_type)
    dec_canonical, dec_qualifier = normalize_class_type(declared, beverage_type)

    # Both resolve to known TTB classes
    if ext_canonical is not None and dec_canonical is not None:
        if ext_canonical == dec_canonical:
            parts = [f"TTB class match: both normalize to '{ext_canonical}'"]
            if ext_qualifier:
                parts.append(f"(extracted qualifier stripped: {ext_qualifier})")
            if dec_qualifier:
                parts.append(f"(declared qualifier stripped: {dec_qualifier})")
            return ("match", 100.0, " ".join(parts))
        else:
            return (
                "content_mismatch",
                0.0,
                f"TTB class mismatch: extracted='{ext_canonical}' vs declared='{dec_canonical}'",
            )

    # At least one didn't resolve -- fall back to fuzzy on stripped text
    # Use the stripped base text (without qualifiers) for fairer comparison
    ext_base = extracted.strip()
    dec_base = declared.strip()

    # If we got canonicals, use them for fuzzy; otherwise use raw
    if ext_canonical:
        ext_base = ext_canonical
    elif ext_qualifier:
        # Qualifiers were stripped but no canonical found; use text minus qualifiers
        from app.services.ttb_classes import _strip_qualifiers
        ext_base, _ = _strip_qualifiers(extracted.strip())

    if dec_canonical:
        dec_base = dec_canonical
    elif dec_qualifier:
        from app.services.ttb_classes import _strip_qualifiers
        dec_base, _ = _strip_qualifiers(declared.strip())

    # Subset word match: if all declared words appear in extracted text, treat as match.
    # Handles cases like declared "Blanco Tequila" vs extracted "Tequila 100% Agave Azul Blanco".
    ext_words = set(normalize_for_fuzzy(ext_base).split())
    dec_words = set(normalize_for_fuzzy(dec_base).split())
    if dec_words and dec_words.issubset(ext_words):
        return ("match", 95.0, f"Subset match: all declared words found in extracted text")

    status, score, fuzzy_reason = fuzzy_match(ext_base, dec_base)

    # Add context about TTB lookup
    notes = []
    if ext_canonical is None:
        notes.append(f"extracted class '{extracted.strip()}' not in TTB list")
    if dec_canonical is None:
        notes.append(f"declared class '{declared.strip()}' not in TTB list")
    ttb_note = "; ".join(notes)

    reason = f"{fuzzy_reason} (fuzzy fallback: {ttb_note})"
    return (status, score, reason)


def specialty_class_match(
    fanciful_name: str | None,
    composition_statement: str | None,
    expected_base_spirit: str | None,
    declared_fanciful_name: str | None = None,
) -> tuple[str, float, str]:
    """Verify a specialty/proprietary product has a fanciful name and/or composition statement.

    Per 27 CFR 5.156, products with administrative COLA codes must display
    a distinctive/fanciful name and a statement of composition on the label.

    Args:
        fanciful_name: The product's distinctive/fanciful name from the label.
        composition_statement: The statement of composition (e.g. "Whisky with honey").
        expected_base_spirit: If set, the composition should reference this spirit.
        declared_fanciful_name: The fanciful name from the COLA application (for verification).

    Returns:
        (status, confidence, reason) tuple.
    """
    has_fanciful = bool(fanciful_name and fanciful_name.strip())
    has_composition = bool(composition_statement and composition_statement.strip())

    if not has_fanciful and not has_composition:
        return ("field_missing", 0.0, "No fanciful name or composition statement found on label")

    # Verify extracted fanciful name against COLA's declared fanciful name
    if declared_fanciful_name and has_fanciful:
        fn_status, fn_score, _ = fuzzy_match(fanciful_name, declared_fanciful_name)
        if fn_status == "content_mismatch":
            # Fallback 1: LLM may put the fanciful name into the composition field
            if has_composition:
                cs_status, _, _ = fuzzy_match(composition_statement, declared_fanciful_name)
                if cs_status == "match":
                    pass  # Fanciful name found in composition — continue to success path
                    fn_status = "match"

            # Fallback 2: Declared fanciful may be a style/variety designator
            # (e.g. "ACHOLADO", "ITALIA", "EXTRA ANEJO") — short ALL-CAPS terms
            # that are COLA metadata, not marketing names on the label
            if fn_status == "content_mismatch":
                decl_words = declared_fanciful_name.strip().split()
                is_style_designator = (
                    len(decl_words) == 1
                    and declared_fanciful_name == declared_fanciful_name.upper()
                )
                if is_style_designator:
                    # Accept if the extracted fanciful has a recognizable product identity
                    # (i.e., it's not empty garbage — it contains meaningful text)
                    if len(fanciful_name.strip().split()) >= 2:
                        pass  # Style designator — skip fanciful name check
                        fn_status = "match"

            if fn_status == "content_mismatch":
                return (
                    "content_mismatch",
                    fn_score,
                    f"Fanciful name mismatch: label has '{fanciful_name}', COLA declares '{declared_fanciful_name}'",
                )

    if has_fanciful and has_composition:
        # Check base spirit if expected
        if expected_base_spirit:
            comp_lower = composition_statement.strip().lower()
            if expected_base_spirit.lower() not in comp_lower:
                return (
                    "extraction_uncertain",
                    70.0,
                    f"Composition '{composition_statement}' does not reference expected base spirit '{expected_base_spirit}'",
                )
        return ("match", 100.0, "Fanciful name and composition statement found")

    # Only one present
    present = "fanciful name" if has_fanciful else "composition statement"
    missing = "composition statement" if has_fanciful else "fanciful name"
    return ("match", 85.0, f"Only {present} found; {missing} not detected")


def numeric_match_abv(
    extracted: str | None, declared: str
) -> tuple[str, float, str | None, str]:
    """Numeric match for ABV with optional proof cross-validation."""
    if not extracted:
        return ("field_missing", 0.0, None, "ABV not found on label")

    ext_abv = extract_abv(extracted)
    dec_abv = extract_abv(declared)

    if ext_abv is None:
        return ("field_missing", 0.0, None, "Could not parse extracted ABV")
    if dec_abv is None:
        return ("content_mismatch", 0.0, "Could not parse declared ABV", "Could not parse declared ABV")

    notes = None

    # Check proof cross-validation if proof is present
    ext_proof = extract_proof(extracted)
    if ext_proof is not None:
        expected_proof = ext_abv * 2
        if abs(ext_proof - expected_proof) > 0.5:
            notes = f"Proof mismatch: {ext_proof} proof != {ext_abv}% ABV x 2 = {expected_proof}"

    # Compare ABV values with small tolerance (0.1%)
    if abs(ext_abv - dec_abv) <= 0.1:
        reason = f"ABV matches within 0.1% tolerance ({ext_abv}% vs {dec_abv}%)"
        return ("match", 100.0, notes, reason)
    reason = f"ABV values differ: {ext_abv}% vs {dec_abv}%"
    return ("content_mismatch", 0.0, notes, reason)


def numeric_match_net_contents(
    extracted: str | None, declared: str
) -> tuple[str, float, str]:
    """Numeric match for net contents with unit normalization.

    Declared may contain multiple values (newline-separated from COLA forms).
    Matches extracted against ANY declared size -- best match wins.
    """
    if not extracted:
        return ("field_missing", 0.0, "Net contents not found on label")

    ext_val, ext_unit = normalize_net_contents(extracted)

    if ext_val is None:
        return ("field_missing", 0.0, "Could not parse extracted net contents")

    def to_ml(val: float, unit: str | None) -> float:
        if unit == "fl oz":
            return val * 29.5735
        return val  # already mL

    ext_ml = to_ml(ext_val, ext_unit)
    ext_label = f"{ext_val}{ext_unit or 'mL'}"

    # Split declared on newlines and try each
    declared_options = [d.strip() for d in declared.split("\n") if d.strip()]
    if not declared_options:
        declared_options = [declared]

    best_match = None
    for dec_str in declared_options:
        dec_val, dec_unit = normalize_net_contents(dec_str)
        if dec_val is None:
            continue

        dec_ml = to_ml(dec_val, dec_unit)
        cross_unit = ext_unit != dec_unit
        tolerance = 5.0 if cross_unit else 0.5
        dec_label = f"{dec_val}{dec_unit or 'mL'}"

        if abs(ext_ml - dec_ml) < tolerance:
            return ("match", 100.0, f"Net contents match within tolerance ({ext_label} vs {dec_label})")

        # Track closest mismatch for reporting
        diff = abs(ext_ml - dec_ml)
        if best_match is None or diff < best_match[0]:
            best_match = (diff, dec_label)

    if best_match is None:
        return ("content_mismatch", 0.0, "Could not parse declared net contents")

    # If values differ by >5x, likely an OCR misread (e.g. 7500 vs 750)
    best_diff, best_dec_label = best_match
    best_dec_ml = ext_ml - best_diff if ext_ml > best_diff else ext_ml + best_diff
    if best_dec_ml > 0:
        ratio = max(ext_ml, best_dec_ml) / min(ext_ml, best_dec_ml)
        if ratio > 5:
            return (
                "extraction_uncertain", 30.0,
                f"Net contents differ by {ratio:.0f}x ({ext_label} vs {best_dec_label}) — possible OCR error",
            )

    return ("content_mismatch", 0.0, f"Net contents differ: {ext_label} vs {best_match[1]}")


def presence_check(extracted: str | None, required: bool) -> tuple[str, float, str]:
    """Presence check for sulfites declaration."""
    if not required:
        return ("match", 100.0, "Sulfites declaration not required")
    if extracted:
        return ("match", 100.0, "Sulfites declaration found")
    return ("field_missing", 0.0, "Required sulfites declaration missing")


class ComparisonService:
    """Dispatches each field to the appropriate matching strategy."""

    FIELD_STRATEGIES = {
        "brand_name": "fuzzy",
        "class_type": "class_type",
        "alcohol_content": "numeric_abv",
        "net_contents": "numeric_net",
        "producer_name": "company_name",
        "producer_address": "address",
        "country_of_origin": "fuzzy",
        "importer_name": "company_name",
        "importer_address": "address",
        "government_warning": "exact",
        "sulfites_declaration": "presence",
    }

    def compare_fields(
        self,
        extracted: dict[str, str | None],
        declared: ApplicationData,
        beverage_type: str,
        extraction_confidences: dict[str, str] | None = None,
    ) -> list[FieldComparisonResult]:
        results = []

        # Map declared fields
        declared_map = {
            "brand_name": declared.brand_name,
            "class_type": declared.class_type,
            "alcohol_content": declared.alcohol_content,
            "net_contents": declared.net_contents,
            "producer_name": declared.producer_name,
            "producer_address": declared.producer_address,
            "country_of_origin": declared.country_of_origin,
            "importer_name": declared.importer_name,
            "importer_address": declared.importer_address,
        }

        for field_name, strategy in self.FIELD_STRATEGIES.items():
            ext_value = extracted.get(field_name)

            if strategy == "exact":
                if ext_value:
                    status, score, reason = exact_match(ext_value, CANONICAL_WARNING)
                else:
                    status, score, reason = "field_missing", 0.0, "Government warning not found on label"
                results.append(
                    FieldComparisonResult(
                        field_name=field_name,
                        declared_value=None,
                        extracted_value=ext_value,
                        status=status,
                        confidence=score,
                        match_strategy="exact",
                        confidence_reason=reason,
                    )
                )

            elif strategy == "presence":
                required = declared.has_sulfites_declaration
                status, score, reason = presence_check(ext_value, required)
                if not required and not ext_value:
                    continue  # Skip sulfites if not required
                results.append(
                    FieldComparisonResult(
                        field_name=field_name,
                        declared_value="Required" if required else "N/A",
                        extracted_value=ext_value,
                        status=status,
                        confidence=score,
                        match_strategy="presence",
                        confidence_reason=reason,
                    )
                )

            elif strategy == "numeric_abv":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    status, score, _notes, reason = numeric_match_abv(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="numeric",
                            confidence_reason=reason,
                        )
                    )

            elif strategy == "numeric_net":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    status, score, reason = numeric_match_net_contents(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="numeric",
                            confidence_reason=reason,
                        )
                    )

            elif strategy == "class_type":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    is_admin, base_spirit = is_administrative_class_type(dec_value)
                    specialty_data = extracted.get("_specialty_class_data")
                    if is_admin and specialty_data:
                        fn = specialty_data.get("fanciful_name")
                        cs = specialty_data.get("composition_statement")
                        status, score, reason = specialty_class_match(
                            fn, cs, base_spirit,
                            declared_fanciful_name=declared.fanciful_name,
                        )
                        # Build display value for extracted
                        parts = [p for p in [fn, cs] if p]
                        ext_display = " — ".join(parts) if parts else None
                        results.append(
                            FieldComparisonResult(
                                field_name=field_name,
                                declared_value=dec_value,
                                extracted_value=ext_display,
                                status=status,
                                confidence=score,
                                match_strategy="specialty_class",
                                confidence_reason=reason,
                            )
                        )
                    else:
                        status, score, reason = class_type_match(
                            ext_value, dec_value, beverage_type
                        )
                        results.append(
                            FieldComparisonResult(
                                field_name=field_name,
                                declared_value=dec_value,
                                extracted_value=ext_value,
                                status=status,
                                confidence=score,
                                match_strategy="class_type",
                                confidence_reason=reason,
                            )
                        )

            elif strategy == "company_name":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    norm_ext = normalize_company_name(ext_value) if ext_value else None
                    norm_dec = normalize_company_name(dec_value)
                    # Single-word containment: if extracted is one meaningful word
                    # contained in the declared name, accept it
                    if (norm_ext and len(norm_ext.split()) == 1
                            and len(norm_ext) >= 3 and norm_ext in norm_dec):
                        status, score, reason = (
                            "match", 95.0,
                            f"Company name '{norm_ext}' found in declared name",
                        )
                    else:
                        status, score, reason = fuzzy_match(norm_ext, norm_dec)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="fuzzy",
                            confidence_reason=reason,
                        )
                    )

            elif strategy == "address":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    status, score, reason = address_match(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="fuzzy",
                            confidence_reason=reason,
                        )
                    )

            elif strategy == "fuzzy":
                dec_value = declared_map.get(field_name)
                if dec_value:  # Only compare if declared
                    ext_cmp = ext_value
                    dec_cmp = dec_value
                    if field_name == "country_of_origin" and ext_cmp:
                        ext_cmp = normalize_country(ext_cmp)
                        dec_cmp = normalize_country(dec_cmp)
                    status, score, reason = fuzzy_match(ext_cmp, dec_cmp)
                    # Brand-specific fallback: use partial_ratio when standard
                    # fuzzy fails — handles declared brand embedded in longer
                    # extracted text and COLA typos (e.g. "VIJO TONEL" vs
                    # "Pisco Viejo Tonel")
                    if (field_name == "brand_name"
                            and status == "content_mismatch" and ext_cmp):
                        pr = fuzz.partial_ratio(
                            normalize_for_fuzzy(ext_cmp),
                            normalize_for_fuzzy(dec_cmp),
                        )
                        if pr >= 85:
                            status, score, reason = (
                                "match", pr,
                                f"Fuzzy match: {pr:.0f}% (brand partial match)",
                            )
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="fuzzy",
                            confidence_reason=reason,
                        )
                    )

        # Apply extraction confidence adjustments
        if extraction_confidences:
            adjusted = []
            for r in results:
                ext_conf = extraction_confidences.get(r.field_name, "high")
                status = r.status
                score = r.confidence
                reason = r.confidence_reason or ""

                if ext_conf == "low":
                    status = "extraction_uncertain"
                    score = min(score, 50.0)
                    reason += f" | Extraction quality: low -- confidence capped at {score:.0f}"
                elif ext_conf == "medium":
                    if status == "content_mismatch":
                        status = "extraction_uncertain"
                        score = min(score, 60.0)
                        reason += f" | Extraction quality: medium -- confidence capped at {score:.0f}"
                    elif status == "match" and score < 92.0:
                        status = "extraction_uncertain"
                        score = min(score, 75.0)
                        reason += f" | Extraction quality: medium -- confidence capped at {score:.0f}"

                adjusted.append(
                    FieldComparisonResult(
                        field_name=r.field_name,
                        declared_value=r.declared_value,
                        extracted_value=r.extracted_value,
                        status=status,
                        confidence=score,
                        match_strategy=r.match_strategy,
                        bounding_box=r.bounding_box,
                        extraction_confidence=ext_conf,
                        confidence_reason=reason,
                    )
                )
            results = adjusted

        return results


class ConfidenceScorer:
    """Calculates overall confidence and verification status."""

    CRITICAL_FIELDS = {
        "government_warning", "brand_name", "class_type",
        "alcohol_content", "net_contents",
    }

    FIELD_WEIGHTS = {
        "government_warning": 2.0,
        "brand_name": 1.5,
        "class_type": 1.5,
        "alcohol_content": 1.5,
        "net_contents": 1.0,
        "producer_name": 1.0,
        "producer_address": 0.5,
        "country_of_origin": 0.8,
        "importer_name": 0.8,
        "importer_address": 0.5,
        "sulfites_declaration": 0.5,
    }

    def calculate(
        self, fields: list[FieldComparisonResult]
    ) -> tuple[float, str]:
        if not fields:
            return (0.0, "fail")

        # Weighted average
        total_weight = 0.0
        weighted_sum = 0.0
        for f in fields:
            w = self.FIELD_WEIGHTS.get(f.field_name, 1.0)
            weighted_sum += f.confidence * w
            total_weight += w
        avg = weighted_sum / total_weight if total_weight > 0 else 0.0

        # 1. Any critical field with field_missing or content_mismatch => fail
        for f in fields:
            if f.field_name in self.CRITICAL_FIELDS and f.status in ("field_missing", "content_mismatch"):
                return (avg, "fail")

        # 2. Any field extraction_uncertain => needs_review
        has_uncertain = any(f.status == "extraction_uncertain" for f in fields)

        # 3. Non-critical field issues
        has_noncritical_issues = any(
            f.status in ("field_missing", "content_mismatch")
            and f.field_name not in self.CRITICAL_FIELDS
            for f in fields
        )

        if has_uncertain:
            return (avg, "needs_review")

        if has_noncritical_issues:
            if avg >= 70.0:
                return (avg, "needs_review")
            else:
                return (avg, "fail")

        # All match
        if avg >= 90.0:
            return (avg, "pass")
        elif avg >= 70.0:
            return (avg, "needs_review")
        else:
            return (avg, "fail")
