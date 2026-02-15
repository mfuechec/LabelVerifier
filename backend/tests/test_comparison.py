import pytest
from app.services.comparison import (
    exact_match,
    fuzzy_match,
    numeric_match_abv,
    numeric_match_net_contents,
    presence_check,
    class_type_match,
    ComparisonService,
    ConfidenceScorer,
    CANONICAL_WARNING,
)


class TestExactMatch:
    def test_canonical_warning_matches(self):
        status, score, _reason = exact_match(CANONICAL_WARNING, CANONICAL_WARNING)
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
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
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
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
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
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
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
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_all_uppercase(self):
        """Labels often print the warning in ALL CAPS -- should still match."""
        text = CANONICAL_WARNING.upper()
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
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
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_with_ocr_mid_word_hyphens_only(self):
        """OCR mid-word hyphens are normalized: ALCO-HOLIC → ALCOHOLIC."""
        text = (
            "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, "
            "WOMEN SHOULD NOT DRINK ALCO-HOLIC BEVERAGES DURING PREGNANCY "
            "BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF "
            "ALCO-HOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
            "OPERATE MACHIN-ERY, AND MAY CAUSE HEALTH PROBLEMS."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_warning_with_ocr_hyphens_plus_other_artifacts(self):
        """Hyphens are fixed but remaining artifacts (RISKS, BIRTHDEFECTS) still cause mismatch."""
        text = (
            "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, "
            "WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY "
            "BECAUSE OF THE RISKS OF BIRTHDEFECTS. (2) CONSUMPTION OF ALCO-"
            "HOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
            "OPERATE MACHIN-ERY, AND MAY CAUSE HEALTH PROBLEMS."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert score > 95.0  # Very close but not exact


class TestFuzzyMatch:
    def test_case_insensitive_match(self):
        status, score, _reason = fuzzy_match("STONE'S THROW", "Stone's Throw")
        assert status == "match"
        assert score >= 85.0

    def test_obvious_mismatch(self):
        status, score, _reason = fuzzy_match("STONE'S THROW", "ROCK'S THROW")
        assert status == "content_mismatch"

    def test_company_name_with_abbreviations(self):
        status, score, _reason = fuzzy_match(
            "Old Tom Distillery, LLC", "OLD TOM DISTILLERY LLC"
        )
        assert status == "match"

    def test_address_abbreviation(self):
        status, score, _reason = fuzzy_match("Louisville, KY", "Louisville, Kentucky")
        assert status == "match"

    def test_none_extracted(self):
        status, score, _reason = fuzzy_match(None, "Test Value")
        assert status == "field_missing"

    def test_empty_extracted(self):
        status, score, _reason = fuzzy_match("", "Test Value")
        assert status == "field_missing"

    def test_umlaut_brand_name_matches(self):
        """Bärenjäger (with umlauts) should match Barenjager (without)."""
        status, score, _reason = fuzzy_match("Bärenjäger", "Barenjager")
        assert status == "match"
        assert score >= 90.0

    def test_accented_characters_match(self):
        """Names with accents should match their ASCII equivalents."""
        status, score, _reason = fuzzy_match("Château Pétrus", "Chateau Petrus")
        assert status == "match"
        assert score >= 90.0


class TestNumericMatchABV:
    def test_same_abv(self):
        status, score, notes, _reason = numeric_match_abv("45%", "45%")
        assert status == "match"
        assert score == 100.0

    def test_abv_with_different_formats(self):
        status, score, notes, _reason = numeric_match_abv("45% Alc./Vol.", "45%")
        assert status == "match"

    def test_abv_with_proof_cross_validation(self):
        status, score, notes, _reason = numeric_match_abv(
            "45% Alc./Vol. (90 Proof)", "45%"
        )
        assert status == "match"
        assert "proof" not in (notes or "").lower() or "valid" in (notes or "").lower()

    def test_abv_with_wrong_proof(self):
        status, score, notes, _reason = numeric_match_abv(
            "45% Alc./Vol. (80 Proof)", "45%"
        )
        assert status == "match"  # ABV matches, but proof mismatch flagged
        assert notes is not None and "proof" in notes.lower()

    def test_abv_mismatch(self):
        status, score, notes, _reason = numeric_match_abv("14.5%", "14.0%")
        assert status == "content_mismatch"

    def test_none_extracted(self):
        status, score, notes, _reason = numeric_match_abv(None, "45%")
        assert status == "field_missing"


class TestNumericMatchNetContents:
    def test_same_ml(self):
        status, score, _reason = numeric_match_net_contents("750 mL", "750 mL")
        assert status == "match"
        assert score == 100.0

    def test_ml_no_space_vs_space(self):
        status, score, _reason = numeric_match_net_contents("750ML", "750 mL")
        assert status == "match"

    def test_cl_vs_ml(self):
        status, score, _reason = numeric_match_net_contents("75cL", "750 mL")
        assert status == "match"

    def test_mismatch(self):
        status, score, _reason = numeric_match_net_contents("375 mL", "750 mL")
        assert status == "content_mismatch"

    def test_floz_vs_ml_match(self):
        """25.4 fl oz should match 750 mL (cross-unit conversion)."""
        status, score, _reason = numeric_match_net_contents("25.4 fl oz", "750 mL")
        assert status == "match"
        assert score == 100.0

    def test_ml_vs_floz_match(self):
        """750 mL should match 25.4 fl oz (reverse direction)."""
        status, score, _reason = numeric_match_net_contents("750 mL", "25.4 fl oz")
        assert status == "match"
        assert score == 100.0

    def test_floz_vs_ml_mismatch(self):
        """12 fl oz should NOT match 750 mL."""
        status, score, _reason = numeric_match_net_contents("12 fl oz", "750 mL")
        assert status == "content_mismatch"

    def test_none_extracted(self):
        status, score, _reason = numeric_match_net_contents(None, "750 mL")
        assert status == "field_missing"


    def test_liter_spelled_out(self):
        """'1 LITER' should match '1 L' (same volume)."""
        status, score, _reason = numeric_match_net_contents("1 LITER", "1 L")
        assert status == "match"
        assert score == 100.0

    def test_litre_spelled_out(self):
        """'1 Litre' should match '1 L' (British spelling)."""
        status, score, _reason = numeric_match_net_contents("1 Litre", "1 L")
        assert status == "match"
        assert score == 100.0

    def test_liters_plural(self):
        """'1.5 Liters' should match '1.5 L'."""
        status, score, _reason = numeric_match_net_contents("1.5 Liters", "1.5 L")
        assert status == "match"
        assert score == 100.0


class TestPresenceCheck:
    def test_present_and_required(self):
        status, score, _reason = presence_check("Contains Sulfites", True)
        assert status == "match"
        assert score == 100.0

    def test_not_present_and_required(self):
        status, score, _reason = presence_check(None, True)
        assert status == "field_missing"
        assert score == 0.0

    def test_not_present_and_not_required(self):
        status, score, _reason = presence_check(None, False)
        assert status == "match"
        assert score == 100.0

    def test_present_and_not_required(self):
        status, score, _reason = presence_check("Contains Sulfites", False)
        assert status == "match"
        assert score == 100.0


class TestCountryNameNormalization:
    """Country of origin should match common native-language variants via ComparisonService."""

    def _compare_country(self, extracted_country: str, declared_country: str):
        """Helper: run comparison with only country_of_origin populated."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test", class_type="Wine",
            alcohol_content="12%", net_contents="750 mL",
            beverage_type="wine",
            country_of_origin=declared_country,
        )
        extracted = {"country_of_origin": extracted_country}
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "wine")
        return next(r for r in results if r.field_name == "country_of_origin")

    def test_italia_matches_italy(self):
        r = self._compare_country("Italia", "Italy")
        assert r.status == "match"
        assert r.confidence >= 85.0

    def test_deutschland_matches_germany(self):
        r = self._compare_country("Deutschland", "Germany")
        assert r.status == "match"
        assert r.confidence >= 85.0

    def test_espana_matches_spain(self):
        r = self._compare_country("España", "Spain")
        assert r.status == "match"
        assert r.confidence >= 85.0

    def test_france_matches_france(self):
        """Same name in both languages -- should still match."""
        r = self._compare_country("France", "France")
        assert r.status == "match"

    def test_mexique_matches_mexico(self):
        r = self._compare_country("México", "Mexico")
        assert r.status == "match"
        assert r.confidence >= 85.0

    def test_holland_matches_the_netherlands(self):
        """'Holland' and 'The Netherlands' are the same country -- common on spirit labels."""
        r = self._compare_country("Holland", "The Netherlands")
        assert r.status == "match"
        assert r.confidence >= 85.0

    def test_the_netherlands_matches_netherlands(self):
        """'The Netherlands' should match 'Netherlands'."""
        r = self._compare_country("The Netherlands", "Netherlands")
        assert r.status == "match"
        assert r.confidence >= 85.0


class TestFuzzyMatchTightening:
    def test_short_token_set_not_inflated(self):
        """'Reserve Rum' vs 'Caribbean Rum' should NOT match -- shared 'Rum' inflates token_set_ratio."""
        status, score, _reason = fuzzy_match("Reserve Rum", "Caribbean Rum")
        assert status == "content_mismatch"

    def test_legitimate_fuzzy_still_passes(self):
        """Existing good fuzzy matches should still work."""
        status, score, _reason = fuzzy_match("OLD TOM DISTILLERY LLC", "Old Tom Distillery, LLC")
        assert status == "match"

    def test_reordered_words_still_match(self):
        """Token reordering should still match (e.g. address components)."""
        status, score, _reason = fuzzy_match("Louisville KY 40202", "KY Louisville 40202")
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


class TestConfidenceReasons:
    """Test that match functions populate confidence_reason strings."""

    def test_exact_match_reason_on_match(self):
        status, score, reason = exact_match(CANONICAL_WARNING, CANONICAL_WARNING)
        assert status == "match"
        assert reason == "Exact match"

    def test_exact_match_reason_on_mismatch(self):
        text = "GOVERNMENT WARNING: wrong text here"
        status, score, reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert "Word-level similarity" in reason

    def test_fuzzy_match_reason_on_match(self):
        status, score, reason = fuzzy_match("OLD TOM DISTILLERY LLC", "Old Tom Distillery, LLC")
        assert status == "match"
        assert "Fuzzy match" in reason
        assert "threshold: 85%" in reason

    def test_fuzzy_match_declared_substring_of_extracted(self):
        """When declared brand is fully contained in extracted text, it should match."""
        status, score, reason = fuzzy_match("Cascade Winery", "Cascade")
        assert status == "match", f"Expected match but got {status}: {reason}"
        assert score >= 85.0

    def test_fuzzy_match_extracted_substring_of_declared(self):
        """When extracted text is fully contained in declared, it should match."""
        status, score, reason = fuzzy_match("Cascade", "Cascade Winery")
        assert status == "match", f"Expected match but got {status}: {reason}"
        assert score >= 85.0

    def test_fuzzy_match_reason_on_mismatch(self):
        status, score, reason = fuzzy_match("COMPLETELY DIFFERENT", "Old Tom Distillery")
        assert status == "content_mismatch"
        assert "below 85% threshold" in reason

    def test_fuzzy_match_reason_field_missing(self):
        status, score, reason = fuzzy_match(None, "Test Value")
        assert status == "field_missing"
        assert "not found" in reason.lower() or "missing" in reason.lower()

    def test_numeric_abv_reason_on_match(self):
        status, score, notes, reason = numeric_match_abv("45%", "45%")
        assert status == "match"
        assert "within 0.1% tolerance" in reason

    def test_numeric_abv_reason_with_proof_note(self):
        status, score, notes, reason = numeric_match_abv("45% Alc./Vol. (80 Proof)", "45%")
        assert status == "match"
        assert "proof" in notes.lower()

    def test_numeric_abv_reason_on_mismatch(self):
        status, score, notes, reason = numeric_match_abv("14.5%", "14.0%")
        assert status == "content_mismatch"
        assert "differ" in reason.lower() or "mismatch" in reason.lower()

    def test_numeric_net_contents_reason_on_match(self):
        status, score, reason = numeric_match_net_contents("750 mL", "750 mL")
        assert status == "match"
        assert "match" in reason.lower()

    def test_numeric_net_contents_reason_on_mismatch(self):
        status, score, reason = numeric_match_net_contents("375 mL", "750 mL")
        assert status == "content_mismatch"
        assert "differ" in reason.lower() or "375" in reason

    def test_presence_check_reason_found(self):
        status, score, reason = presence_check("Contains Sulfites", True)
        assert status == "match"
        assert "found" in reason.lower()

    def test_presence_check_reason_missing(self):
        status, score, reason = presence_check(None, True)
        assert status == "field_missing"
        assert "missing" in reason.lower()

    def test_presence_check_reason_not_required(self):
        status, score, reason = presence_check(None, False)
        assert status == "match"
        assert "not required" in reason.lower()


class TestComparisonServiceConfidenceReasons:
    """Test that ComparisonService.compare_fields populates new fields."""

    def test_compare_fields_populates_confidence_reason(self):
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test Brand", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST BRAND",
            "class_type": "BOURBON",
            "alcohol_content": "45% Alc./Vol.",
            "net_contents": "750 mL",
            "government_warning": CANONICAL_WARNING,
        }
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        for r in results:
            assert r.confidence_reason is not None, f"{r.field_name} missing confidence_reason"

    def test_compare_fields_populates_extraction_confidence(self):
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
        assert brand.extraction_confidence == "low"
        assert "Extraction quality: low" in brand.confidence_reason

    def test_compare_fields_high_conf_extraction_confidence(self):
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
        assert brand.extraction_confidence == "high"


class TestClassTypeMatch:
    def test_same_canonical_class_both_known(self):
        """Both values resolve to the same canonical class -- match."""
        status, score, reason = class_type_match(
            "Kentucky Straight Bourbon Whiskey", "Straight Bourbon Whiskey", "distilled_spirits"
        )
        assert status == "match"
        assert score == 100.0

    def test_same_canonical_different_qualifiers(self):
        """Same base class, different finishing qualifiers -- match."""
        status, score, reason = class_type_match(
            "Bourbon Whiskey Finished in Port Wine Barrels",
            "Bourbon Whiskey",
            "distilled_spirits",
        )
        assert status == "match"
        assert score == 100.0

    def test_different_canonical_classes(self):
        """Different canonical classes -- content_mismatch."""
        status, score, reason = class_type_match(
            "Vodka", "Bourbon Whiskey", "distilled_spirits"
        )
        assert status == "content_mismatch"

    def test_declared_not_in_ttb_list_fuzzy_fallback_match(self):
        """Declared class not in TTB list -- falls back to fuzzy, should still match if similar."""
        status, score, reason = class_type_match(
            "Artisanal Moonshine", "Artisanal Moonshine", "distilled_spirits"
        )
        assert status == "match"

    def test_declared_not_in_ttb_list_fuzzy_fallback_mismatch(self):
        """Both unknown and different -- fuzzy mismatch."""
        status, score, reason = class_type_match(
            "Artisanal Moonshine", "Craft Cider", "distilled_spirits"
        )
        assert status == "content_mismatch"

    def test_none_extracted(self):
        """None extracted value -- field_missing."""
        status, score, reason = class_type_match(
            None, "Bourbon Whiskey", "distilled_spirits"
        )
        assert status == "field_missing"

    def test_empty_extracted(self):
        """Empty extracted value -- field_missing."""
        status, score, reason = class_type_match(
            "", "Bourbon Whiskey", "distilled_spirits"
        )
        assert status == "field_missing"

    def test_whisky_vs_whiskey_spelling(self):
        """Whisky and whiskey variants should match via normalization."""
        status, score, reason = class_type_match(
            "Bourbon Whisky", "Bourbon Whiskey", "distilled_spirits"
        )
        assert status == "match"
        assert score == 100.0

    def test_wine_class_match(self):
        status, score, reason = class_type_match("Red Wine", "Red Wine", "wine")
        assert status == "match"
        assert score == 100.0

    def test_beer_class_match(self):
        status, score, reason = class_type_match("Ale", "Ale", "malt_beverages")
        assert status == "match"
        assert score == 100.0

    def test_reason_explains_normalization(self):
        """Reason should mention normalization when qualifiers are stripped."""
        status, score, reason = class_type_match(
            "Bourbon Whiskey Finished in Oak Barrels",
            "Bourbon Whiskey",
            "distilled_spirits",
        )
        assert status == "match"
        assert "normaliz" in reason.lower() or "canonical" in reason.lower() or "class" in reason.lower()


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


class TestGovernmentWarningRejections:
    """Verify that non-exact government warnings are correctly rejected.

    Per TTB requirements, the government warning must be word-for-word exact.
    These tests cover real-world deviations agents encounter: creative wording,
    truncated text, missing sections, and subtle word substitutions.
    """

    def test_title_case_prefix_still_matches(self):
        """'Government Warning:' in title case is accepted (case-insensitive)."""
        text = (
            "Government Warning: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "match"

    def test_missing_pregnancy_clause_is_rejected(self):
        """Omitting 'during pregnancy' changes the meaning -- must fail."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages because of the "
            "risk of birth defects. (2) Consumption of alcoholic beverages "
            "impairs your ability to drive a car or operate machinery, "
            "and may cause health problems."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"

    def test_substituted_word_impairs_vs_affects(self):
        """Replacing 'impairs' with 'affects' -- subtle word swap must fail."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages affects your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"

    def test_missing_section_2_entirely(self):
        """Warning with only section (1) -- section (2) omitted entirely."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert score < 80.0  # Substantially different

    def test_missing_section_1_entirely(self):
        """Warning with only section (2) -- section (1) omitted entirely."""
        text = (
            "GOVERNMENT WARNING: (2) Consumption of alcoholic beverages "
            "impairs your ability to drive a car or operate machinery, "
            "and may cause health problems."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert score < 70.0  # Substantially different -- missing entire section

    def test_completely_missing_warning(self):
        """No warning extracted at all -- should be field_missing via ComparisonService."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "BOURBON",
            "alcohol_content": "45%",
            "net_contents": "750 mL",
            # government_warning intentionally omitted
        }
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "field_missing"
        assert warning.confidence == 0.0

    def test_missing_warning_fails_overall(self):
        """Missing government warning (critical field) should produce overall 'fail'."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "BOURBON",
            "alcohol_content": "45%",
            "net_contents": "750 mL",
        }
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        scorer = ConfidenceScorer()
        _avg, status = scorer.calculate(results)
        assert status == "fail"

    def test_mismatched_warning_fails_overall(self):
        """Wrong warning wording (critical field mismatch) should produce overall 'fail'."""
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "BOURBON",
            "alcohol_content": "45%",
            "net_contents": "750 mL",
            "government_warning": (
                "GOVERNMENT WARNING: (1) According to the Surgeon General, "
                "women should not drink alcoholic beverages because of the "
                "risk of birth defects. (2) Consumption of alcoholic beverages "
                "affects your ability to drive a car or operate machinery, "
                "and may cause health problems."
            ),
        }
        service = ComparisonService()
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        scorer = ConfidenceScorer()
        _avg, status = scorer.calculate(results)
        assert status == "fail"

    def test_truncated_warning_text(self):
        """Warning that cuts off mid-sentence should fail."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability"
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"

    def test_extra_text_appended(self):
        """Warning with extra text appended should fail exact match."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems. "
            "Drink responsibly."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"

    def test_missing_government_warning_prefix(self):
        """Warning text without the 'GOVERNMENT WARNING:' prefix should fail."""
        text = (
            "(1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"

    def test_reworded_health_problems_ending(self):
        """Changing 'health problems' to 'health issues' should fail."""
        text = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health issues."
        )
        status, score, _reason = exact_match(text, CANONICAL_WARNING)
        assert status == "content_mismatch"


class TestImperfectImageExtraction:
    """Verify that low-confidence extractions from imperfect images
    (bad angles, glare, stylized fonts) produce extraction_uncertain status
    rather than false pass/fail results.
    """

    def _run_comparison_with_confidences(
        self, extracted: dict, confidences: dict, beverage_type: str = "distilled_spirits"
    ):
        from app.models.schemas import ApplicationData
        app_data = ApplicationData(
            brand_name="Test Brand", class_type="Bourbon",
            alcohol_content="45%", net_contents="750 mL",
            beverage_type=beverage_type,
        )
        service = ComparisonService()
        return service.compare_fields(
            extracted, app_data, beverage_type,
            extraction_confidences=confidences,
        )

    def test_low_confidence_warning_becomes_uncertain(self):
        """Government warning extracted with low confidence (e.g. glare on label)
        should become extraction_uncertain, not a false pass or fail."""
        results = self._run_comparison_with_confidences(
            extracted={"government_warning": CANONICAL_WARNING},
            confidences={"government_warning": "low"},
        )
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "extraction_uncertain"
        assert warning.confidence <= 50.0

    def test_low_confidence_warning_triggers_needs_review(self):
        """An extraction_uncertain on a critical field should produce needs_review overall."""
        results = self._run_comparison_with_confidences(
            extracted={
                "brand_name": "TEST BRAND",
                "class_type": "BOURBON",
                "alcohol_content": "45%",
                "net_contents": "750 mL",
                "government_warning": CANONICAL_WARNING,
            },
            confidences={"government_warning": "low"},
        )
        scorer = ConfidenceScorer()
        _avg, status = scorer.calculate(results)
        assert status == "needs_review"

    def test_medium_confidence_mismatch_becomes_uncertain(self):
        """Medium confidence + content mismatch (e.g. bad OCR from angle)
        should become extraction_uncertain -- the mismatch might be OCR error."""
        results = self._run_comparison_with_confidences(
            extracted={"government_warning": "GOVERNMENT WARNING: partially readable text"},
            confidences={"government_warning": "medium"},
        )
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "extraction_uncertain"
        assert warning.confidence <= 60.0

    def test_high_confidence_mismatch_stays_mismatch(self):
        """High confidence + content mismatch = genuine mismatch, not uncertainty."""
        results = self._run_comparison_with_confidences(
            extracted={
                "government_warning": (
                    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
                    "women should not drink alcoholic beverages because of the "
                    "risk of birth defects."
                )
            },
            confidences={"government_warning": "high"},
        )
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "content_mismatch"

    def test_multiple_fields_low_confidence_all_uncertain(self):
        """Simulates a badly-lit photo where multiple fields have low extraction confidence."""
        results = self._run_comparison_with_confidences(
            extracted={
                "brand_name": "TEST BRAND",
                "alcohol_content": "45%",
                "government_warning": CANONICAL_WARNING,
            },
            confidences={
                "brand_name": "low",
                "alcohol_content": "low",
                "government_warning": "low",
            },
        )
        for r in results:
            if r.field_name in ("brand_name", "alcohol_content", "government_warning"):
                assert r.status == "extraction_uncertain", (
                    f"{r.field_name} should be uncertain with low confidence"
                )

    def test_medium_confidence_mismatch_becomes_uncertain(self):
        """Medium confidence + mismatch from garbled OCR should become uncertain.
        A badly angled photo might produce unrecognizable text for brand name."""
        results = self._run_comparison_with_confidences(
            extracted={"brand_name": "TSET BNRAD"},  # garbled from bad image
            confidences={"brand_name": "medium"},
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        # Garbled text produces a content_mismatch, which at medium confidence
        # should become extraction_uncertain
        assert brand.status == "extraction_uncertain"
        assert brand.confidence <= 60.0
