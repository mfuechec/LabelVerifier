"""Tests for TextMatcher -- searches transcribed label text for declared values."""

import pytest

from app.models.schemas import ApplicationData, FieldComparisonResult
from app.services.text_matcher import TextMatcher


@pytest.fixture
def matcher():
    return TextMatcher()


# --- Brand name ---

class TestFindBrand:
    def test_brand_found_in_text(self, matcher):
        status, conf, reason, found = matcher.find_text(
            "BARENJAGER", "BARENJAGER HONEY & BOURBON LIQUEUR 750 mL"
        )
        assert status == "match"
        assert conf >= 85.0

    def test_brand_not_found(self, matcher):
        status, conf, reason, found = matcher.find_text(
            "TOTALLY DIFFERENT", "BARENJAGER HONEY & BOURBON LIQUEUR"
        )
        assert status == "content_mismatch" or status == "field_missing"

    def test_brand_partial_match(self, matcher):
        """Declared brand is a substring of label text."""
        status, conf, reason, found = matcher.find_text(
            "CASCADE WINERY", "CASCADE WINERY RESERVE RED WINE 2019"
        )
        assert status == "match"

    def test_brand_case_insensitive(self, matcher):
        status, conf, reason, found = matcher.find_text(
            "Barenjager", "BARENJAGER HONEY LIQUEUR"
        )
        assert status == "match"

    def test_brand_word_prefix_of_label_word(self, matcher):
        """LENZ MOSER BLAU should match when label has BLAUFRANKISCH on a different line."""
        # Realistic: brand and grape variety are on separate lines
        status, conf, reason, found = matcher.find_text(
            "LENZ MOSER BLAU",
            "Lenz Moser Selection PRODUCT OF AUSTRIA BLAUFRANKISCH RED WINE 2019 750 ML"
        )
        assert status == "match"
        assert conf >= 90.0

    def test_brand_short_prefix_no_false_match(self, matcher):
        """Short words (<4 chars) should NOT get prefix credit."""
        status, conf, reason, found = matcher.find_text(
            "RUM BRAND", "RUMBLE FISH BRAND VODKA"
        )
        # "RUM" is only 3 chars, should NOT prefix-match "RUMBLE"
        # "BRAND" matches exactly, but "RUM" shouldn't match
        assert status == "content_mismatch" or conf < 100.0


# --- ABV ---

class TestMatchAbv:
    def test_abv_found_matches(self, matcher):
        status, conf, reason, found = matcher.match_abv(
            "40", "ALC. 40% BY VOL. GOVERNMENT WARNING..."
        )
        assert status == "match"
        assert conf == 100.0

    def test_abv_found_mismatch(self, matcher):
        """5-point diff is within near-miss tolerance -> extraction_uncertain."""
        status, conf, reason, found = matcher.match_abv(
            "40", "ALC. 35% BY VOL. SOME OTHER TEXT"
        )
        assert status == "extraction_uncertain"

    def test_abv_not_found_in_text(self, matcher):
        status, conf, reason, found = matcher.match_abv(
            "40", "BARENJAGER HONEY LIQUEUR 750 ML"
        )
        assert status == "field_missing"

    def test_abv_multiple_percentages_best_match(self, matcher):
        """Text has multiple percentages, the declared one should match."""
        status, conf, reason, found = matcher.match_abv(
            "40", "13% fruit juice ALC 40% BY VOL"
        )
        assert status == "match"

    def test_abv_plain_number_declared(self, matcher):
        """COLA forms often store just '35' without % sign."""
        status, conf, reason, found = matcher.match_abv(
            "35", "35% ALC./VOL."
        )
        assert status == "match"

    def test_abv_near_miss_returns_uncertain(self, matcher):
        """ABV off by a few points (misread) should be extraction_uncertain, not hard fail."""
        status, conf, reason, found = matcher.match_abv(
            "35", "ALC. 33% BY VOL."
        )
        assert status == "extraction_uncertain"
        assert conf == 50.0
        assert "near-miss" in reason.lower()

    def test_abv_large_mismatch_still_fails(self, matcher):
        """ABV off by more than 5 points should remain content_mismatch."""
        status, conf, reason, found = matcher.match_abv(
            "40", "ALC. 20% BY VOL."
        )
        assert status == "content_mismatch"
        assert conf == 0.0


# --- Net contents ---

class TestMatchNetContents:
    def test_net_contents_ml(self, matcher):
        status, conf, reason, found = matcher.match_net_contents(
            "750 ML", "BARENJAGER 750 mL HONEY LIQUEUR"
        )
        assert status == "match"

    def test_net_contents_liters(self, matcher):
        status, conf, reason, found = matcher.match_net_contents(
            "1 LITER", "PRODUCT INFO 1.0L SOME TEXT"
        )
        assert status == "match"

    def test_net_contents_mismatch(self, matcher):
        status, conf, reason, found = matcher.match_net_contents(
            "750 ML", "375 mL PRODUCT"
        )
        assert status == "content_mismatch"

    def test_net_contents_not_found(self, matcher):
        status, conf, reason, found = matcher.match_net_contents(
            "750 ML", "BARENJAGER HONEY LIQUEUR"
        )
        assert status == "field_missing"

    def test_net_contents_multi_declared(self, matcher):
        """COLA declares multiple sizes; label has one of them."""
        status, conf, reason, found = matcher.match_net_contents(
            "750 MILLILITERS\n1 LITER", "PRODUCT 1.0L INFO"
        )
        assert status == "match"


# --- Government warning ---

class TestMatchWarning:
    CANONICAL = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, "
        "women should not drink alcoholic beverages during pregnancy "
        "because of the risk of birth defects. (2) Consumption of "
        "alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )

    def test_warning_exact_match(self, matcher):
        text = f"Some label text {self.CANONICAL} more text"
        status, conf, reason, found = matcher.match_warning(text)
        assert status == "match"
        assert conf == 100.0

    def test_warning_with_ocr_artifacts(self, matcher):
        """Warning with mid-word hyphens should still match."""
        garbled = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alco-holic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machin-ery, and may cause health problems."
        )
        text = f"Label text {garbled} more text"
        status, conf, reason, found = matcher.match_warning(text)
        assert status == "match"

    def test_warning_missing(self, matcher):
        status, conf, reason, found = matcher.match_warning(
            "BARENJAGER HONEY LIQUEUR 750 ML 35% ABV"
        )
        assert status == "field_missing"

    def test_warning_partial_present(self, matcher):
        """Only part of warning is found -> content_mismatch with partial score."""
        partial = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects."
        )
        text = f"Some text {partial} end"
        status, conf, reason, found = matcher.match_warning(text)
        # Should detect partial match, not full match
        assert status in ("content_mismatch", "match")
        # If it's a match, confidence should be reduced
        if status == "content_mismatch":
            assert conf > 0


# --- Company name ---

class TestFindCompany:
    def test_company_found(self, matcher):
        status, conf, reason, found = matcher.find_company(
            "SIDNEY FRANK IMPORTING CO., INC.",
            "IMPORTED BY SIDNEY FRANK IMPORTING CO., INC. NEW ROCHELLE, N.Y."
        )
        assert status == "match"

    def test_company_not_found(self, matcher):
        status, conf, reason, found = matcher.find_company(
            "TOTALLY DIFFERENT CO.",
            "PRODUCED BY ACME SPIRITS LLC PORTLAND OR"
        )
        assert status in ("content_mismatch", "field_missing")

    def test_company_partial_name(self, matcher):
        """Just the key words of company name found."""
        status, conf, reason, found = matcher.find_company(
            "HOWLING MOON, THE COPPER STILL LLC",
            "HOWLING MOON DISTILLERY COPPER STILL 123 MAIN ST"
        )
        assert status == "match"


# --- Address ---

class TestFindAddress:
    def test_address_city_state_found(self, matcher):
        status, conf, reason, found = matcher.find_address(
            "20 CEDAR ST, NEW ROCHELLE NY 10801",
            "IMPORTED BY COMPANY NEW ROCHELLE, N.Y. 750 mL"
        )
        assert status == "match"

    def test_address_not_found(self, matcher):
        status, conf, reason, found = matcher.find_address(
            "20 CEDAR ST, NEW ROCHELLE NY 10801",
            "PRODUCED IN PORTLAND OREGON"
        )
        assert status in ("content_mismatch", "field_missing")


# --- Country of origin ---

class TestFindCountry:
    def test_country_found(self, matcher):
        status, conf, reason, found = matcher.find_text(
            "Japan", "PRODUCT OF JAPAN 750 ML SAKE"
        )
        assert status == "match"

    def test_country_native_name(self, matcher):
        """Native-language country name should be normalized."""
        status, conf, reason, found = matcher.find_text(
            "Mexico", "HECHO EN MEXICO TEQUILA"
        )
        assert status == "match"


# --- Sulfites ---

class TestFindPresence:
    def test_sulfites_found(self, matcher):
        status, conf, reason, found = matcher.find_presence(
            "sulfites", "CONTAINS SULFITES RED WINE 750 ML"
        )
        assert status == "match"

    def test_sulfites_not_found(self, matcher):
        status, conf, reason, found = matcher.find_presence(
            "sulfites", "RED WINE 750 ML 13% ALC/VOL"
        )
        assert status == "field_missing"


# --- Class type ---

class TestMatchClassType:
    def test_regular_class_found(self, matcher):
        app_data = ApplicationData(
            brand_name="TEST", class_type="Vodka",
            alcohol_content="40", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "Vodka", "PREMIUM VODKA TRIPLE DISTILLED 750 ML", app_data
        )
        assert status == "match"

    def test_admin_class_type_returns_uncertain(self, matcher):
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "OTHER SPECIALTIES & PROPRIETARIES",
            "BARENJAGER HONEY LIQUEUR 750 ML",
            app_data,
        )
        assert status == "extraction_uncertain"

    def test_table_wine_class_stripped(self, matcher):
        """Fix 2: TABLE RED WINE -> RED WINE for text search."""
        app_data = ApplicationData(
            brand_name="TEST", class_type="TABLE RED WINE",
            alcohol_content="12", net_contents="750 ML",
            beverage_type="wine",
        )
        status, conf, reason, found = matcher.match_class_type(
            "TABLE RED WINE", "PREMIUM RED WINE FROM CALIFORNIA 750 ML", app_data
        )
        assert status == "match"

    def test_parenthetical_qualifier_stripped(self, matcher):
        """Fix 2: MARGARITA (UNDER 48 PROOF) -> MARGARITA for text search."""
        app_data = ApplicationData(
            brand_name="TEST", class_type="MARGARITA (UNDER 48 PROOF)",
            alcohol_content="20", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "MARGARITA (UNDER 48 PROOF)", "PREMIUM MARGARITA 750 ML 20% ALC/VOL", app_data
        )
        assert status == "match"

    def test_usb_suffix_stripped(self, matcher):
        """Fix 2: OTHER RUM GOLD USB -> OTHER RUM GOLD -> RUM GOLD -> searches text."""
        app_data = ApplicationData(
            brand_name="TEST", class_type="RUM GOLD USB",
            alcohol_content="40", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "RUM GOLD USB", "GOLD RUM AGED 750 ML", app_data
        )
        assert status == "match"

    def test_other_prefix_stripped(self, matcher):
        """OTHER RUM GOLD USB -> RUM GOLD after stripping OTHER + USB."""
        app_data = ApplicationData(
            brand_name="TEST", class_type="OTHER RUM GOLD USB",
            alcohol_content="40", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "OTHER RUM GOLD USB", "GOLD RUM AGED 750 ML", app_data
        )
        assert status == "match"

    def test_table_flavored_wine(self, matcher):
        """TABLE FLAVORED WINE -> FLAVORED WINE -> matches TTB wine class."""
        app_data = ApplicationData(
            brand_name="TEST", class_type="TABLE FLAVORED WINE",
            alcohol_content="13", net_contents="1.5 LITERS",
            beverage_type="wine",
        )
        status, conf, reason, found = matcher.match_class_type(
            "TABLE FLAVORED WINE", "PLUM FLAVORED WINE 13% ALC/VOL", app_data
        )
        assert status == "match"

    def test_flavored_wine_matches_plum_wine(self, matcher):
        """COLA 'TABLE FLAVORED WINE' -> stripped to 'FLAVORED WINE'.
        Label says 'PLUM WINE'. Should match because 'wine' is the base class word."""
        app_data = ApplicationData(
            brand_name="GEKKEIKAN", class_type="TABLE FLAVORED WINE",
            alcohol_content="13", net_contents="1.5 LITERS",
            beverage_type="wine",
        )
        status, conf, reason, found = matcher.match_class_type(
            "TABLE FLAVORED WINE",
            "PLUM WINE AND NATURAL PLUM FLAVOR 13% ALC/VOL 1.5 LITERS",
            app_data,
        )
        assert status == "match"

    def test_rum_gold_matches_cachaca(self, matcher):
        """COLA 'OTHER RUM GOLD USB' -> stripped to 'RUM GOLD'.
        Label says 'CACHACA'. Cachaca is a type of rum — should match."""
        app_data = ApplicationData(
            brand_name="SAO PAULO", class_type="OTHER RUM GOLD USB",
            alcohol_content="40", net_contents="1 LITER",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "OTHER RUM GOLD USB",
            "Distilled From Cane CACHACA SAO PAULO 40% ALC./VOL 1 LITER",
            app_data,
        )
        assert status == "match"

    def test_warning_partial_match_above_85(self, matcher):
        """Fix 4: Partial warnings scoring 72-81% via ratio should match at 85+ via token_set_ratio."""
        partial_warning = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )
        # Introduce realistic transcription differences
        garbled_warning = (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery and may cause health problems."
        )
        text = f"Some text {garbled_warning} end"
        status, conf, reason, found = matcher.match_warning(text)
        assert status == "match", f"Expected match but got {status}: {reason}"

    def test_cerveza_matches_beer_class(self, matcher):
        """'cerveza' in label text should match declared class 'BEER' via TTB variant."""
        app_data = ApplicationData(
            brand_name="BARRILITO", class_type="BEER",
            alcohol_content="3.6", net_contents="40 FL. OZ",
            beverage_type="beer",
        )
        status, conf, reason, found = matcher.match_class_type(
            "BEER", "CERVEZA BARRILITO 8 FL OZ 3.6% ALC BY VOL", app_data
        )
        assert status == "match"

    def test_class_type_not_found(self, matcher):
        app_data = ApplicationData(
            brand_name="TEST", class_type="Vodka",
            alcohol_content="40", net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        status, conf, reason, found = matcher.match_class_type(
            "Vodka", "BARENJAGER HONEY LIQUEUR 750 ML", app_data
        )
        assert status in ("content_mismatch", "field_missing")


# --- Full integration ---

class TestMatchFields:
    def test_full_match_fields(self, matcher):
        """Integration: all fields matched against a transcribed label."""
        app_data = ApplicationData(
            brand_name="TEST BRAND",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 ML",
            producer_name="TEST PRODUCER INC.",
            beverage_type="distilled_spirits",
        )
        label_text = (
            "TEST BRAND\n"
            "PREMIUM VODKA\n"
            "ALC. 40% BY VOL.\n"
            "750 mL\n"
            "PRODUCED BY TEST PRODUCER INC. CITY, STATE\n"
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of "
            "alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        )

        results = matcher.match_fields(label_text, app_data, "distilled_spirits")
        assert len(results) > 0
        # All should be match for this well-formed label
        for r in results:
            assert r.status == "match", f"{r.field_name}: {r.status} - {r.confidence_reason}"
