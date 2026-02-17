"""TextMatcher -- search transcribed label text for declared field values.

Replaces structured field extraction + comparison with direct text search.
Each field uses a specific matching strategy against the full transcribed text.
"""

import re
import logging

from rapidfuzz import fuzz

from app.models.schemas import ApplicationData, FieldComparisonResult
from app.services.normalizer import (
    normalize_whitespace,
    normalize_warning_text,
    normalize_for_fuzzy,
    normalize_company_name,
    normalize_country,
    extract_abv,
    normalize_net_contents,
)
from app.services.comparison import (
    CANONICAL_WARNING,
    FUZZY_THRESHOLD,
    _normalize_address_tokens,
    specialty_class_match,
)
from app.services.ttb_classes import (
    is_administrative_class_type,
    normalize_class_type,
)

logger = logging.getLogger(__name__)


class TextMatcher:
    """Search for declared field values in transcribed label text."""

    def match_fields(
        self,
        label_text: str,
        declared: ApplicationData,
        beverage_type: str,
        specialty_class_data: dict | None = None,
    ) -> list[FieldComparisonResult]:
        """Run all field matchers against transcribed text.

        Args:
            label_text: Full transcribed text from all label panels.
            declared: Application data with declared values.
            beverage_type: One of "distilled_spirits", "wine", "beer".
            specialty_class_data: Optional dict with fanciful_name/composition_statement
                for admin class codes (from separate LLM call).

        Returns:
            List of FieldComparisonResult for each compared field.
        """
        results = []

        # Brand name
        if declared.brand_name:
            status, conf, reason, found = self.find_text(
                declared.brand_name, label_text
            )
            # Brand-specific: also try partial_ratio for embedded matches
            if status == "content_mismatch":
                pr = fuzz.partial_ratio(
                    normalize_for_fuzzy(declared.brand_name),
                    normalize_for_fuzzy(label_text),
                )
                if pr >= 85:
                    status, conf, reason = "match", pr, f"Brand found via partial match: {pr:.0f}%"
            results.append(FieldComparisonResult(
                field_name="brand_name",
                declared_value=declared.brand_name,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Class type
        if declared.class_type:
            is_admin, base_spirit = is_administrative_class_type(declared.class_type)
            if is_admin and specialty_class_data:
                fn = specialty_class_data.get("fanciful_name")
                cs = specialty_class_data.get("composition_statement")
                status, conf, reason = specialty_class_match(
                    fn, cs, base_spirit,
                    declared_fanciful_name=declared.fanciful_name,
                )
                parts = [p for p in [fn, cs] if p]
                ext_display = " — ".join(parts) if parts else None
                results.append(FieldComparisonResult(
                    field_name="class_type",
                    declared_value=declared.class_type,
                    extracted_value=ext_display,
                    status=status,
                    confidence=conf,
                    match_strategy="specialty_class",
                    confidence_reason=reason,
                ))
            else:
                status, conf, reason, found = self.match_class_type(
                    declared.class_type, label_text, declared
                )
                results.append(FieldComparisonResult(
                    field_name="class_type",
                    declared_value=declared.class_type,
                    extracted_value=found,
                    status=status,
                    confidence=conf,
                    match_strategy="text_search",
                    confidence_reason=reason,
                ))

        # Alcohol content
        if declared.alcohol_content:
            status, conf, reason, found = self.match_abv(
                declared.alcohol_content, label_text
            )
            results.append(FieldComparisonResult(
                field_name="alcohol_content",
                declared_value=declared.alcohol_content,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="numeric",
                confidence_reason=reason,
            ))

        # Net contents
        if declared.net_contents:
            status, conf, reason, found = self.match_net_contents(
                declared.net_contents, label_text
            )
            results.append(FieldComparisonResult(
                field_name="net_contents",
                declared_value=declared.net_contents,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="numeric",
                confidence_reason=reason,
            ))

        # Producer name
        if declared.producer_name:
            status, conf, reason, found = self.find_company(
                declared.producer_name, label_text
            )
            results.append(FieldComparisonResult(
                field_name="producer_name",
                declared_value=declared.producer_name,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Producer address
        if declared.producer_address:
            status, conf, reason, found = self.find_address(
                declared.producer_address, label_text
            )
            results.append(FieldComparisonResult(
                field_name="producer_address",
                declared_value=declared.producer_address,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Country of origin
        if declared.country_of_origin:
            status, conf, reason, found = self.find_text(
                declared.country_of_origin, label_text
            )
            results.append(FieldComparisonResult(
                field_name="country_of_origin",
                declared_value=declared.country_of_origin,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Importer name
        if declared.importer_name:
            status, conf, reason, found = self.find_company(
                declared.importer_name, label_text
            )
            results.append(FieldComparisonResult(
                field_name="importer_name",
                declared_value=declared.importer_name,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Importer address
        if declared.importer_address:
            status, conf, reason, found = self.find_address(
                declared.importer_address, label_text
            )
            results.append(FieldComparisonResult(
                field_name="importer_address",
                declared_value=declared.importer_address,
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="text_search",
                confidence_reason=reason,
            ))

        # Government warning
        status, conf, reason, found = self.match_warning(label_text)
        results.append(FieldComparisonResult(
            field_name="government_warning",
            declared_value=None,
            extracted_value=found,
            status=status,
            confidence=conf,
            match_strategy="exact",
            confidence_reason=reason,
        ))

        # Sulfites
        if declared.has_sulfites_declaration:
            status, conf, reason, found = self.find_presence(
                "sulfites", label_text
            )
            results.append(FieldComparisonResult(
                field_name="sulfites_declaration",
                declared_value="Required",
                extracted_value=found,
                status=status,
                confidence=conf,
                match_strategy="presence",
                confidence_reason=reason,
            ))

        return results

    def find_text(
        self, declared_value: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Fuzzy word-presence search in transcribed text.

        Returns (status, confidence, reason, found_value).
        """
        if not declared_value or not text:
            return ("field_missing", 0.0, "No text to search", None)

        norm_declared = normalize_for_fuzzy(declared_value)
        norm_text = normalize_for_fuzzy(text)

        if not norm_declared:
            return ("field_missing", 0.0, "Empty declared value", None)

        # Check if declared words appear in text
        declared_words = set(norm_declared.split())
        text_words = set(norm_text.split())

        # Direct containment: all declared words found in text
        if declared_words.issubset(text_words):
            return ("match", 100.0, "All declared words found in text", declared_value)

        # Try token_set_ratio for partial/reordered matches
        tsr = fuzz.token_set_ratio(norm_declared, norm_text)
        if tsr >= FUZZY_THRESHOLD:
            return ("match", tsr, f"Token set match: {tsr:.0f}%", declared_value)

        # Try partial_ratio for substring containment
        pr = fuzz.partial_ratio(norm_declared, norm_text)
        if pr >= 90:
            return ("match", pr, f"Partial match: {pr:.0f}%", declared_value)

        # Not found
        best = max(tsr, pr)
        return (
            "content_mismatch", best,
            f"Best match: {best:.0f}% (below threshold)", None,
        )

    def match_abv(
        self, declared_value: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Regex for ABV patterns in text, numeric comparison against declared."""
        dec_abv = extract_abv(declared_value)
        if dec_abv is None:
            return ("field_missing", 0.0, "Could not parse declared ABV", None)

        # Find all percentage patterns in text
        percentages = re.findall(r"(\d+\.?\d*)\s*%", text)
        if not percentages:
            return ("field_missing", 0.0, "No percentage found in label text", None)

        # Check if any percentage matches declared ABV
        for pct_str in percentages:
            pct = float(pct_str)
            if abs(pct - dec_abv) <= 0.1:
                return (
                    "match", 100.0,
                    f"ABV matches: {pct}% found in text vs {dec_abv}% declared",
                    f"{pct}%",
                )

        # Find closest mismatch
        closest = min(percentages, key=lambda p: abs(float(p) - dec_abv))
        return (
            "content_mismatch", 0.0,
            f"ABV mismatch: {closest}% in text vs {dec_abv}% declared",
            f"{closest}%",
        )

    def match_net_contents(
        self, declared_value: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Regex for volume patterns in text, numeric comparison with unit conversion."""
        # Parse declared (may be multi-line)
        declared_options = [d.strip() for d in declared_value.split("\n") if d.strip()]
        if not declared_options:
            declared_options = [declared_value]

        declared_sizes = []
        for dec_str in declared_options:
            val, unit = normalize_net_contents(dec_str)
            if val is not None:
                declared_sizes.append((val, unit, dec_str))

        if not declared_sizes:
            return ("field_missing", 0.0, "Could not parse declared net contents", None)

        # Find volume patterns in text
        volume_patterns = [
            (r"(\d+\.?\d*)\s*[Mm][Ll]\b", "mL"),
            (r"(\d+\.?\d*)\s*fl\.?\s*oz", "fl oz"),
            (r"(\d+\.?\d*)\s*cL\b", "cL"),
            (r"(\d+\.?\d*)\s*(?:Liters?|Litres?|L)\b", "L"),
            (r"(\d+\.?\d*)\s*MILLILITERS?\b", "mL"),
        ]

        found_volumes = []
        for pattern, unit_label in volume_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                raw_val = float(m.group(1))
                # Convert to mL
                if unit_label == "fl oz":
                    ml_val = raw_val * 29.5735
                elif unit_label == "cL":
                    ml_val = raw_val * 10.0
                elif unit_label == "L":
                    ml_val = raw_val * 1000.0
                else:
                    ml_val = raw_val
                found_volumes.append((ml_val, m.group(0).strip()))

        if not found_volumes:
            return ("field_missing", 0.0, "No volume found in label text", None)

        def to_ml(val, unit):
            if unit == "fl oz":
                return val * 29.5735
            return val  # already mL

        # Check if any found volume matches any declared size
        for dec_val, dec_unit, dec_str in declared_sizes:
            dec_ml = to_ml(dec_val, dec_unit)
            for found_ml, found_str in found_volumes:
                tolerance = 5.0  # mL
                if abs(found_ml - dec_ml) < tolerance:
                    return (
                        "match", 100.0,
                        f"Net contents match: {found_str} vs {dec_str}",
                        found_str,
                    )

        # No match found
        best_found = found_volumes[0][1] if found_volumes else None
        return (
            "content_mismatch", 0.0,
            f"Net contents mismatch: found {best_found} vs declared {declared_value}",
            best_found,
        )

    def match_warning(
        self, text: str
    ) -> tuple[str, float, str, str | None]:
        """Check if canonical government warning appears in text."""
        if not text:
            return ("field_missing", 0.0, "No text to search", None)

        # Normalize both for comparison
        norm_text = normalize_warning_text(text).lower()
        norm_canonical = normalize_warning_text(CANONICAL_WARNING).lower()

        # Check if canonical warning is a substring
        if norm_canonical in norm_text:
            return ("match", 100.0, "Government warning found (exact match)", CANONICAL_WARNING)

        # Check word-by-word overlap: look for "government warning" anchor
        gw_pos = norm_text.find("government warning")
        if gw_pos == -1:
            return ("field_missing", 0.0, "Government warning not found in text", None)

        # Extract the warning section (from "government warning" to a reasonable end)
        warning_section = norm_text[gw_pos:]
        # Limit to ~500 chars (warning is ~300 chars)
        warning_section = warning_section[:500]

        # Compare extracted section to canonical
        ratio = fuzz.ratio(warning_section, norm_canonical)
        if ratio >= 90:
            return ("match", 100.0, f"Government warning found (similarity: {ratio:.0f}%)", CANONICAL_WARNING)

        if ratio >= 70:
            return (
                "content_mismatch", ratio,
                f"Government warning partially matched: {ratio:.0f}%",
                warning_section[:300],
            )

        return (
            "content_mismatch", ratio,
            f"Government warning present but differs: {ratio:.0f}%",
            warning_section[:300],
        )

    def find_company(
        self, declared_value: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Company name search with legal suffix normalization."""
        if not declared_value or not text:
            return ("field_missing", 0.0, "No text to search", None)

        norm_declared = normalize_company_name(declared_value)
        norm_text = normalize_company_name(text)

        if not norm_declared:
            return ("field_missing", 0.0, "Empty declared company name", None)

        # Check if all normalized declared words appear in text
        declared_words = set(norm_declared.split())
        text_words = set(norm_text.split())

        if declared_words.issubset(text_words):
            return ("match", 100.0, "All company name words found in text", declared_value)

        # Single-word containment: if declared has one key word found in text
        if len(declared_words) >= 1:
            found_words = declared_words & text_words
            if found_words and len(found_words) >= max(1, len(declared_words) * 0.5):
                ratio = len(found_words) / len(declared_words) * 100
                if ratio >= 60:
                    return (
                        "match", min(ratio, 95.0),
                        f"Company name partially matched: {len(found_words)}/{len(declared_words)} words found",
                        declared_value,
                    )

        # Fuzzy fallback on full normalized strings
        tsr = fuzz.token_set_ratio(norm_declared, norm_text)
        if tsr >= FUZZY_THRESHOLD:
            return ("match", tsr, f"Company fuzzy match: {tsr:.0f}%", declared_value)

        return (
            "content_mismatch", tsr,
            f"Company name not found: best match {tsr:.0f}%", None,
        )

    def find_address(
        self, declared_value: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Address token search -- city/state tokens from declared should appear in text."""
        if not declared_value or not text:
            return ("field_missing", 0.0, "No text to search", None)

        dec_tokens = _normalize_address_tokens(declared_value)
        text_tokens = _normalize_address_tokens(text)

        if not dec_tokens:
            return ("field_missing", 0.0, "Could not parse declared address", None)

        # Check if key address tokens appear in the text
        found_tokens = dec_tokens & text_tokens
        if found_tokens and len(found_tokens) >= max(1, len(dec_tokens) * 0.4):
            ratio = len(found_tokens) / len(dec_tokens) * 100
            if ratio >= 50:
                return (
                    "match", min(ratio, 100.0),
                    f"Address tokens found: {found_tokens}",
                    declared_value,
                )

        # Fuzzy fallback
        norm_dec = normalize_for_fuzzy(declared_value)
        norm_text = normalize_for_fuzzy(text)
        pr = fuzz.partial_ratio(norm_dec, norm_text)
        if pr >= FUZZY_THRESHOLD:
            return ("match", pr, f"Address partial match: {pr:.0f}%", declared_value)

        return (
            "content_mismatch", pr,
            f"Address not found in text: {pr:.0f}%", None,
        )

    def find_presence(
        self, keyword: str, text: str
    ) -> tuple[str, float, str, str | None]:
        """Simple keyword presence check (e.g., sulfites)."""
        if not text:
            return ("field_missing", 0.0, "No text to search", None)

        norm_text = text.lower()
        if keyword.lower() in norm_text:
            return ("match", 100.0, f"'{keyword}' found in text", f"Contains {keyword.title()}")

        return ("field_missing", 0.0, f"'{keyword}' not found in text", None)

    def match_class_type(
        self, declared_value: str, text: str, app_data: ApplicationData
    ) -> tuple[str, float, str, str | None]:
        """Class type matching against transcribed text.

        For admin codes, returns extraction_uncertain (requires separate LLM call).
        For regular classes, searches for class words in text.
        """
        is_admin, _ = is_administrative_class_type(declared_value)
        if is_admin:
            return (
                "extraction_uncertain", 50.0,
                "Administrative class code -- requires LLM specialty extraction",
                None,
            )

        # Normalize declared class
        dec_canonical, _ = normalize_class_type(declared_value, app_data.beverage_type)
        search_term = dec_canonical or declared_value

        # Search for class words in text
        norm_search = normalize_for_fuzzy(search_term)
        norm_text = normalize_for_fuzzy(text)

        # Check if all class words appear in text
        search_words = set(norm_search.split())
        text_words = set(norm_text.split())

        if search_words.issubset(text_words):
            return ("match", 100.0, f"Class '{search_term}' found in text", search_term)

        # Try fuzzy partial match
        pr = fuzz.partial_ratio(norm_search, norm_text)
        tsr = fuzz.token_set_ratio(norm_search, norm_text)
        best = max(pr, tsr)

        if best >= FUZZY_THRESHOLD:
            return ("match", best, f"Class fuzzy match: {best:.0f}%", search_term)

        return (
            "content_mismatch", best,
            f"Class '{search_term}' not found in text: {best:.0f}%", None,
        )
