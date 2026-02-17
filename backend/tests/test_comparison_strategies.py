"""Tests for individual comparison strategies."""

import pytest
from app.services.comparison import (
    exact_match,
    fuzzy_match,
    class_type_match,
    numeric_match_abv,
    numeric_match_net_contents,
    presence_check,
    specialty_class_match,
    CANONICAL_WARNING,
)


class TestExactMatch:
    def test_identical(self):
        status, score, _ = exact_match(CANONICAL_WARNING, CANONICAL_WARNING)
        assert status == "match"
        assert score == 100.0

    def test_case_insensitive(self):
        status, _, _ = exact_match(CANONICAL_WARNING.lower(), CANONICAL_WARNING)
        assert status == "match"

    def test_extra_whitespace(self):
        text = CANONICAL_WARNING.replace("  ", "    ")
        status, _, _ = exact_match(text, CANONICAL_WARNING)
        assert status == "match"

    def test_ocr_hyphens(self):
        text = CANONICAL_WARNING.replace("alcoholic", "alco-holic")
        status, _, reason = exact_match(text, CANONICAL_WARNING)
        assert status == "match"
        assert "OCR" in reason

    def test_mismatch(self):
        status, score, _ = exact_match("GOVERNMENT WARNING: wrong text", CANONICAL_WARNING)
        assert status == "content_mismatch"
        assert score < 100.0


class TestFuzzyMatch:
    def test_identical(self):
        status, score, _ = fuzzy_match("BARENJAGER", "BARENJAGER")
        assert status == "match"
        assert score >= 95.0

    def test_close_match(self):
        status, _, _ = fuzzy_match("BARENJAGER HONEY", "BARENJAGER")
        assert status == "match"

    def test_diacritics(self):
        """Diacritics should be normalized before comparison."""
        status, _, _ = fuzzy_match("Bärenjäger", "BARENJAGER")
        assert status == "match"

    def test_mismatch(self):
        status, _, _ = fuzzy_match("SMIRNOFF", "BARENJAGER")
        assert status == "content_mismatch"

    def test_missing(self):
        status, _, _ = fuzzy_match(None, "BARENJAGER")
        assert status == "field_missing"

    def test_empty_extracted(self):
        status, _, _ = fuzzy_match("", "BARENJAGER")
        assert status == "field_missing"

    def test_containment(self):
        """Extracted value contains declared value."""
        status, _, _ = fuzzy_match(
            "HOWLING MOON THE COPPER STILL LLC",
            "HOWLING MOON"
        )
        assert status == "match"


class TestClassTypeMatch:
    def test_exact_ttb_class(self):
        status, score, _ = class_type_match("Vodka", "VODKA", "distilled_spirits")
        assert status == "match"
        assert score == 100.0

    def test_subset_match(self):
        """All declared words found in extracted text."""
        status, _, _ = class_type_match(
            "Tequila 100% Agave Azul Blanco",
            "Blanco Tequila",
            "distilled_spirits",
        )
        assert status == "match"

    def test_missing(self):
        status, _, _ = class_type_match(None, "VODKA", "distilled_spirits")
        assert status == "field_missing"

    def test_mismatch_classes(self):
        status, _, _ = class_type_match("GIN", "VODKA", "distilled_spirits")
        assert status == "content_mismatch"


class TestNumericMatchAbv:
    def test_exact_match(self):
        status, score, _, _ = numeric_match_abv("40% ABV", "40%")
        assert status == "match"
        assert score == 100.0

    def test_tolerance(self):
        status, _, _, _ = numeric_match_abv("39.95%", "40%")
        assert status == "match"

    def test_plain_number_declared(self):
        """COLA stores ABV as plain number (e.g., '35')."""
        status, _, _, _ = numeric_match_abv("35% ABV", "35")
        assert status == "match"

    def test_mismatch(self):
        status, _, _, _ = numeric_match_abv("40%", "50%")
        assert status == "content_mismatch"

    def test_missing(self):
        status, _, _, _ = numeric_match_abv(None, "40%")
        assert status == "field_missing"

    def test_proof_cross_validation(self):
        """Proof should be 2x ABV."""
        status, _, notes, _ = numeric_match_abv("40% ABV 80 Proof", "40%")
        assert status == "match"
        assert notes is None  # 80 proof = 40% x 2, consistent

    def test_proof_mismatch(self):
        """Proof inconsistent with ABV should be noted."""
        status, _, notes, _ = numeric_match_abv("40% ABV 100 Proof", "40%")
        assert status == "match"  # ABV still matches
        assert notes is not None  # But proof is wrong


class TestNumericMatchNetContents:
    def test_same_unit(self):
        status, score, _ = numeric_match_net_contents("750 mL", "750 mL")
        assert status == "match"

    def test_spelled_out_vs_abbreviated(self):
        """COLA uses 'MILLILITERS', label may show 'mL'."""
        status, _, _ = numeric_match_net_contents("750 mL", "750 MILLILITERS")
        assert status == "match"

    def test_cross_unit_conversion(self):
        status, _, _ = numeric_match_net_contents("25.4 fl oz", "750 mL")
        assert status == "match"

    def test_multi_value_declared_match(self):
        """Declared has multiple sizes, extracted matches one."""
        declared = "375 MILLILITERS\n750 MILLILITERS\n1 LITER"
        status, _, _ = numeric_match_net_contents("750 mL", declared)
        assert status == "match"

    def test_multi_value_declared_match_liter(self):
        declared = "750 MILLILITERS\n1 LITER"
        status, _, _ = numeric_match_net_contents("1 L", declared)
        assert status == "match"

    def test_multi_value_declared_mismatch(self):
        declared = "375 MILLILITERS\n750 MILLILITERS"
        status, _, _ = numeric_match_net_contents("1 L", declared)
        assert status == "content_mismatch"

    def test_mismatch(self):
        status, _, _ = numeric_match_net_contents("750 mL", "1 L")
        assert status == "content_mismatch"

    def test_missing(self):
        status, _, _ = numeric_match_net_contents(None, "750 mL")
        assert status == "field_missing"


class TestPresenceCheck:
    def test_required_and_present(self):
        status, _, _ = presence_check("Contains Sulfites", True)
        assert status == "match"

    def test_required_but_missing(self):
        status, _, _ = presence_check(None, True)
        assert status == "field_missing"

    def test_not_required(self):
        status, _, _ = presence_check(None, False)
        assert status == "match"


class TestSpecialtyClassMatch:
    """Tests for specialty/proprietary class verification via fanciful name + composition."""

    def test_both_present_no_base_spirit(self):
        """Both fanciful name and composition present, no base spirit check."""
        status, score, reason = specialty_class_match(
            "Ecstasy", "Liqueur with natural flavors", None
        )
        assert status == "match"
        assert score == 100.0

    def test_only_fanciful_name(self):
        """Only fanciful name present -- lower confidence match."""
        status, score, reason = specialty_class_match(
            "Ecstasy", None, None
        )
        assert status == "match"
        assert score == 85.0

    def test_only_composition(self):
        """Only composition statement present -- lower confidence match."""
        status, score, reason = specialty_class_match(
            None, "Whisky with honey", None
        )
        assert status == "match"
        assert score == 85.0

    def test_neither_present(self):
        """Neither fanciful name nor composition -- field_missing."""
        status, score, reason = specialty_class_match(
            None, None, None
        )
        assert status == "field_missing"
        assert score == 0.0

    def test_base_spirit_found_in_composition(self):
        """Expected base spirit appears in composition statement."""
        status, score, reason = specialty_class_match(
            "Honey Bee", "Whisky with honey", "whisky"
        )
        assert status == "match"
        assert score == 100.0

    def test_base_spirit_missing_from_composition(self):
        """Expected base spirit NOT found in composition -- extraction_uncertain."""
        status, score, reason = specialty_class_match(
            "Honey Bee", "Rum with spices", "whisky"
        )
        assert status == "extraction_uncertain"

    def test_base_spirit_no_composition_to_check(self):
        """Base spirit expected but no composition statement to verify."""
        status, score, reason = specialty_class_match(
            "Honey Bee", None, "whisky"
        )
        assert status == "match"
        assert score == 85.0

    def test_empty_strings_treated_as_none(self):
        """Empty strings should be treated as missing."""
        status, score, reason = specialty_class_match(
            "", "", None
        )
        assert status == "field_missing"

    # Fix #3/#4: Verify extracted fanciful name against COLA declared fanciful name
    def test_declared_fanciful_matches_extracted(self):
        """When COLA declares a fanciful name and label matches, full confidence."""
        status, score, reason = specialty_class_match(
            "Midnight Moonshine", "Corn whiskey with flavors", None,
            declared_fanciful_name="MIDNIGHT MOONSHINE",
        )
        assert status == "match"
        assert score == 100.0

    def test_declared_fanciful_mismatches_extracted(self):
        """When COLA declares a fanciful name and label has a different one, content_mismatch."""
        status, score, reason = specialty_class_match(
            "Totally Different Product", "Corn whiskey with flavors", None,
            declared_fanciful_name="MIDNIGHT MOONSHINE",
        )
        assert status == "content_mismatch"

    def test_declared_fanciful_not_found_on_label(self):
        """COLA declares fanciful name but label extraction found nothing."""
        status, score, reason = specialty_class_match(
            None, "Corn whiskey with flavors", None,
            declared_fanciful_name="MIDNIGHT MOONSHINE",
        )
        # Still a match (composition found) but at lower confidence
        assert status == "match"
        assert score == 85.0

    def test_no_declared_fanciful_skips_check(self):
        """When COLA has no fanciful name, don't penalize."""
        status, score, reason = specialty_class_match(
            "Ecstasy", "Liqueur with natural flavors", None,
            declared_fanciful_name=None,
        )
        assert status == "match"
        assert score == 100.0

    def test_declared_fanciful_substring_of_extracted(self):
        """COLA declares 'BIZAN BARLEY', label has 'GEKKEIKAN BIZAN' — declared words
        are a subset of the extracted fanciful name, should match."""
        status, score, reason = specialty_class_match(
            "GEKKEIKAN BIZAN", "BARLEY SHOCHU SPIRITS DISTILLED FROM BARLEY", None,
            declared_fanciful_name="BIZAN BARLEY",
        )
        assert status == "match"

    def test_declared_fanciful_partial_subset_of_extracted(self):
        """COLA declares 'BIZAN SWEET POTATO', label has 'GEKKEIKAN BIZAN' +
        composition mentions sweet potato — declared words partially in extracted."""
        status, score, reason = specialty_class_match(
            "GEKKEIKAN BIZAN", "SWEET POTATO SHOCHU SPIRITS DISTILLED FROM SWEET POTATO", None,
            declared_fanciful_name="BIZAN SWEET POTATO",
        )
        assert status == "match"

    def test_declared_fanciful_stem_match_in_composition(self):
        """COLA declares 'SPICED RUM', label has 'SAILOR JERRY' +
        composition 'Caribbean Rum with spice...' — 'spiced' should stem-match 'spice'."""
        status, score, reason = specialty_class_match(
            "SAILOR JERRY",
            "Caribbean Rum with spice, caramel and other natural flavors",
            "rum",
            declared_fanciful_name="SPICED RUM",
        )
        assert status == "match"
