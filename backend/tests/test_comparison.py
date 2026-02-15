import pytest
from app.services.comparison import (
    exact_match,
    fuzzy_match,
    numeric_match_abv,
    numeric_match_net_contents,
    presence_check,
    ComparisonService,
    CANONICAL_WARNING,
)


class TestExactMatch:
    def test_canonical_warning_matches(self):
        status, score = exact_match(CANONICAL_WARNING, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_with_extra_whitespace(self):
        text = (
            "GOVERNMENT WARNING:  (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects.  (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_with_line_breaks(self):
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General,\n"
            "women should not drink alcoholic beverages during pregnancy\n"
            "because of the risk of birth defects. (2) Consumption of\n"
            "alcoholic beverages impairs your ability to drive a car\n"
            "or operate machinery, and may cause health problems."
        )
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_wrong_wording(self):
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages because of the "
            "risk of birth defects. (2) Consumption of alcoholic beverages "
            "impairs your ability to drive a car or operate machinery, "
            "and may cause health problems."
        )
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert score < 100.0

    def test_warning_not_all_caps_prefix(self):
        """Case differences should still match (case-insensitive comparison)."""
        text = (
            "Government Warning: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_all_uppercase(self):
        """Labels often print the warning in ALL CAPS -- should still match."""
        text = CANONICAL_WARNING.upper()
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_with_hyphenation(self):
        """Hyphenated line breaks like BEV-\\nERAGES should be normalized."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic bev-\nerages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0


class TestFuzzyMatch:
    def test_case_insensitive_match(self):
        status, score = fuzzy_match("STONE'S THROW", "Stone's Throw")
        assert status == "match"
        assert score >= 85.0

    def test_obvious_mismatch(self):
        status, score = fuzzy_match("STONE'S THROW", "ROCK'S THROW")
        assert status == "content_mismatch"

    def test_company_name_with_abbreviations(self):
        status, score = fuzzy_match(
            "Old Tom Distillery, LLC", "OLD TOM DISTILLERY LLC"
        )
        assert status == "match"

    def test_address_abbreviation(self):
        status, score = fuzzy_match("Louisville, KY", "Louisville, Kentucky")
        assert status == "match"

    def test_none_extracted(self):
        status, score = fuzzy_match(None, "Test Value")
        assert status == "field_missing"

    def test_empty_extracted(self):
        status, score = fuzzy_match("", "Test Value")
        assert status == "field_missing"


class TestNumericMatchABV:
    def test_same_abv(self):
        status, score, notes = numeric_match_abv("45%", "45%")
        assert status == "match"
        assert score == 100.0

    def test_abv_with_different_formats(self):
        status, score, notes = numeric_match_abv("45% Alc./Vol.", "45%")
        assert status == "match"

    def test_abv_with_proof_cross_validation(self):
        status, score, notes = numeric_match_abv(
            "45% Alc./Vol. (90 Proof)", "45%"
        )
        assert status == "match"
        assert "proof" not in (notes or "").lower() or "valid" in (notes or "").lower()

    def test_abv_with_wrong_proof(self):
        status, score, notes = numeric_match_abv(
            "45% Alc./Vol. (80 Proof)", "45%"
        )
        assert status == "match"  # ABV matches, but proof mismatch flagged
        assert notes is not None and "proof" in notes.lower()

    def test_abv_mismatch(self):
        status, score, notes = numeric_match_abv("14.5%", "14.0%")
        assert status == "content_mismatch"

    def test_none_extracted(self):
        status, score, notes = numeric_match_abv(None, "45%")
        assert status == "field_missing"


class TestNumericMatchNetContents:
    def test_same_ml(self):
        status, score = numeric_match_net_contents("750 mL", "750 mL")
        assert status == "match"
        assert score == 100.0

    def test_ml_no_space_vs_space(self):
        status, score = numeric_match_net_contents("750ML", "750 mL")
        assert status == "match"

    def test_cl_vs_ml(self):
        status, score = numeric_match_net_contents("75cL", "750 mL")
        assert status == "match"

    def test_mismatch(self):
        status, score = numeric_match_net_contents("375 mL", "750 mL")
        assert status == "content_mismatch"

    def test_floz_vs_ml_match(self):
        """25.4 fl oz should match 750 mL (cross-unit conversion)."""
        status, score = numeric_match_net_contents("25.4 fl oz", "750 mL")
        assert status == "match"
        assert score == 100.0

    def test_ml_vs_floz_match(self):
        """750 mL should match 25.4 fl oz (reverse direction)."""
        status, score = numeric_match_net_contents("750 mL", "25.4 fl oz")
        assert status == "match"
        assert score == 100.0

    def test_floz_vs_ml_mismatch(self):
        """12 fl oz should NOT match 750 mL."""
        status, score = numeric_match_net_contents("12 fl oz", "750 mL")
        assert status == "content_mismatch"

    def test_none_extracted(self):
        status, score = numeric_match_net_contents(None, "750 mL")
        assert status == "field_missing"


class TestPresenceCheck:
    def test_present_and_required(self):
        status, score = presence_check("Contains Sulfites", True)
        assert status == "match"
        assert score == 100.0

    def test_not_present_and_required(self):
        status, score = presence_check(None, True)
        assert status == "field_missing"
        assert score == 0.0

    def test_not_present_and_not_required(self):
        status, score = presence_check(None, False)
        assert status == "match"
        assert score == 100.0

    def test_present_and_not_required(self):
        status, score = presence_check("Contains Sulfites", False)
        assert status == "match"
        assert score == 100.0


class TestFuzzyMatchTightening:
    def test_short_token_set_not_inflated(self):
        """'Reserve Rum' vs 'Caribbean Rum' should NOT match -- shared 'Rum' inflates token_set_ratio."""
        status, score = fuzzy_match("Reserve Rum", "Caribbean Rum")
        assert status == "content_mismatch"

    def test_legitimate_fuzzy_still_passes(self):
        """Existing good fuzzy matches should still work."""
        status, score = fuzzy_match("OLD TOM DISTILLERY LLC", "Old Tom Distillery, LLC")
        assert status == "match"

    def test_reordered_words_still_match(self):
        """Token reordering should still match (e.g. address components)."""
        status, score = fuzzy_match("Louisville KY 40202", "KY Louisville 40202")
        assert status == "match"


class TestComparisonServiceExtractionConfidence:
    def test_low_conf_converts_match_to_extraction_uncertain(self):
        """Low extraction confidence should convert any result to extraction_uncertain."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test Brand", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {"brand_name": "TEST BRAND"}
        service = ComparisonService()
        results = service.compare_fields(
            extracted, app_data, "distilled_spirits",
            extraction_confidences={"brand_name": "low"},
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        assert brand.status == "extraction_uncertain"
        assert brand.confidence <= 50.0

    def test_medium_conf_converts_mismatch_to_extraction_uncertain(self):
        """Medium conf + content_mismatch should become extraction_uncertain."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test Brand", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {"brand_name": "COMPLETELY DIFFERENT"}
        service = ComparisonService()
        results = service.compare_fields(
            extracted, app_data, "distilled_spirits",
            extraction_confidences={"brand_name": "medium"},
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        assert brand.status == "extraction_uncertain"
        assert brand.confidence <= 60.0

    def test_high_conf_preserves_original_status(self):
        """High confidence should not change the status."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test Brand", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {"brand_name": "TEST BRAND"}
        service = ComparisonService()
        results = service.compare_fields(
            extracted, app_data, "distilled_spirits",
            extraction_confidences={"brand_name": "high"},
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        assert brand.status == "match"


class TestComparisonService:
    def test_compare_all_fields_spirits(self):
        from app.models.schemas import ApplicationData

        app_data = ApplicationData(
            brand_name="Test Brand",
            class_type="Bourbon Whiskey",
            alcohol_content="45%",
            net_contents="750 mL",
            producer_name="Test Distillery",
            producer_address="Louisville, KY",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST BRAND",
            "class_type": "BOURBON WHISKEY",
            "alcohol_content": "45% Alc./Vol.",
            "net_contents": "750 mL",
            "producer_name": "Test Distillery",
            "producer_address": "Louisville, KY",
            "government_warning": CANONICAL_WARNING,
        }
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "distilled_spirits")

        # Should have results for all compared fields
        field_names = [r.field_name for r in results]
        assert "brand_name" in field_names
        assert "government_warning" in field_names

        # All should match
        for r in results:
            if r.field_name != "government_warning":
                assert r.status == "match", f"{r.field_name} should match"
