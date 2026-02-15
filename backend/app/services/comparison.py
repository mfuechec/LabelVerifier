from rapidfuzz import fuzz
from app.services.normalizer import (
    normalize_whitespace,
    normalize_for_fuzzy,
    extract_abv,
    extract_proof,
    normalize_net_contents,
)
from app.models.schemas import ApplicationData, FieldComparisonResult


CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

FUZZY_THRESHOLD = 85.0


def exact_match(extracted: str, canonical: str) -> tuple[str, float]:
    """Case-insensitive exact match after whitespace normalization. Used for government warning."""
    norm_ext = normalize_whitespace(extracted).lower()
    norm_can = normalize_whitespace(canonical).lower()

    if norm_ext == norm_can:
        return ("match", 100.0)

    # Calculate word-level similarity for partial credit
    ratio = fuzz.ratio(norm_ext, norm_can)
    return ("content_mismatch", ratio)


def fuzzy_match(
    extracted: str | None, declared: str, threshold: float = FUZZY_THRESHOLD
) -> tuple[str, float]:
    """Fuzzy match for brand name, producer, address, country, etc."""
    if not extracted:
        return ("field_missing", 0.0)

    norm_ext = normalize_for_fuzzy(extracted)
    norm_dec = normalize_for_fuzzy(declared)

    if not norm_ext:
        return ("field_missing", 0.0)

    # Blend strict and lenient ratios to prevent short-token inflation
    strict_ratio = max(fuzz.ratio(norm_ext, norm_dec), fuzz.token_sort_ratio(norm_ext, norm_dec))
    lenient_ratio = max(fuzz.token_set_ratio(norm_ext, norm_dec), fuzz.partial_ratio(norm_ext, norm_dec))
    best_ratio = 0.7 * strict_ratio + 0.3 * lenient_ratio

    if best_ratio >= threshold:
        return ("match", best_ratio)
    return ("content_mismatch", best_ratio)


def numeric_match_abv(
    extracted: str | None, declared: str
) -> tuple[str, float, str | None]:
    """Numeric match for ABV with optional proof cross-validation."""
    if not extracted:
        return ("field_missing", 0.0, None)

    ext_abv = extract_abv(extracted)
    dec_abv = extract_abv(declared)

    if ext_abv is None:
        return ("field_missing", 0.0, None)
    if dec_abv is None:
        return ("content_mismatch", 0.0, "Could not parse declared ABV")

    notes = None

    # Check proof cross-validation if proof is present
    ext_proof = extract_proof(extracted)
    if ext_proof is not None:
        expected_proof = ext_abv * 2
        if abs(ext_proof - expected_proof) > 0.5:
            notes = f"Proof mismatch: {ext_proof} proof != {ext_abv}% ABV x 2 = {expected_proof}"

    # Compare ABV values with small tolerance (0.1%)
    if abs(ext_abv - dec_abv) <= 0.1:
        return ("match", 100.0, notes)
    return ("content_mismatch", 0.0, notes)


def numeric_match_net_contents(
    extracted: str | None, declared: str
) -> tuple[str, float]:
    """Numeric match for net contents with unit normalization."""
    if not extracted:
        return ("field_missing", 0.0)

    ext_val, ext_unit = normalize_net_contents(extracted)
    dec_val, dec_unit = normalize_net_contents(declared)

    if ext_val is None:
        return ("field_missing", 0.0)
    if dec_val is None:
        return ("content_mismatch", 0.0)

    # Normalize both to mL for comparison
    def to_ml(val: float, unit: str | None) -> float:
        if unit == "fl oz":
            return val * 29.5735
        return val  # already mL

    ext_ml = to_ml(ext_val, ext_unit)
    dec_ml = to_ml(dec_val, dec_unit)

    # Use tighter tolerance for same-unit, wider for cross-unit conversions
    cross_unit = ext_unit != dec_unit
    tolerance = 5.0 if cross_unit else 0.5

    if abs(ext_ml - dec_ml) < tolerance:
        return ("match", 100.0)
    return ("content_mismatch", 0.0)


def presence_check(extracted: str | None, required: bool) -> tuple[str, float]:
    """Presence check for sulfites declaration."""
    if not required:
        return ("match", 100.0)
    if extracted:
        return ("match", 100.0)
    return ("field_missing", 0.0)


class ComparisonService:
    """Dispatches each field to the appropriate matching strategy."""

    FIELD_STRATEGIES = {
        "brand_name": "fuzzy",
        "class_type": "fuzzy",
        "alcohol_content": "numeric_abv",
        "net_contents": "numeric_net",
        "producer_name": "fuzzy",
        "producer_address": "fuzzy",
        "country_of_origin": "fuzzy",
        "importer_name": "fuzzy",
        "importer_address": "fuzzy",
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
                    status, score = exact_match(ext_value, CANONICAL_WARNING)
                else:
                    status, score = "field_missing", 0.0
                results.append(
                    FieldComparisonResult(
                        field_name=field_name,
                        declared_value=None,
                        extracted_value=ext_value,
                        status=status,
                        confidence=score,
                        match_strategy="exact",
                    )
                )

            elif strategy == "presence":
                required = declared.has_sulfites_declaration
                status, score = presence_check(ext_value, required)
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
                    )
                )

            elif strategy == "numeric_abv":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    status, score, _notes = numeric_match_abv(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="numeric",
                        )
                    )

            elif strategy == "numeric_net":
                dec_value = declared_map.get(field_name)
                if dec_value:
                    status, score = numeric_match_net_contents(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="numeric",
                        )
                    )

            elif strategy == "fuzzy":
                dec_value = declared_map.get(field_name)
                if dec_value:  # Only compare if declared
                    status, score = fuzzy_match(ext_value, dec_value)
                    results.append(
                        FieldComparisonResult(
                            field_name=field_name,
                            declared_value=dec_value,
                            extracted_value=ext_value,
                            status=status,
                            confidence=score,
                            match_strategy="fuzzy",
                        )
                    )

        # Apply extraction confidence adjustments
        if extraction_confidences:
            adjusted = []
            for r in results:
                ext_conf = extraction_confidences.get(r.field_name, "high")
                status = r.status
                score = r.confidence

                if ext_conf == "low":
                    status = "extraction_uncertain"
                    score = min(score, 50.0)
                elif ext_conf == "medium":
                    if status == "content_mismatch":
                        status = "extraction_uncertain"
                        score = min(score, 60.0)
                    elif status == "match" and score < 92.0:
                        status = "extraction_uncertain"
                        score = min(score, 75.0)

                adjusted.append(
                    FieldComparisonResult(
                        field_name=r.field_name,
                        declared_value=r.declared_value,
                        extracted_value=r.extracted_value,
                        status=status,
                        confidence=score,
                        match_strategy=r.match_strategy,
                        bounding_box=r.bounding_box,
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
