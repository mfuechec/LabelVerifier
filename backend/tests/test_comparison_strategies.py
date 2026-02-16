"""Tests for individual comparison strategies."""

import pytest
from app.services.comparison import (
    exact_match,
    fuzzy_match,
    class_type_match,
    numeric_match_abv,
    numeric_match_net_contents,
    presence_check,
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
