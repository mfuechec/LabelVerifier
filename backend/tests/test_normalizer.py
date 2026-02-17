"""Tests for text normalization functions."""

import pytest
from app.services.normalizer import (
    normalize_whitespace,
    normalize_warning_text,
    extract_abv,
    extract_proof,
    normalize_net_contents,
    normalize_country,
    normalize_for_fuzzy,
)


class TestNormalizeWhitespace:
    def test_collapses_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_removes_hyphenated_breaks(self):
        assert normalize_whitespace("BEV-\nERAGES") == "BEVERAGES"

    def test_trims(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_empty(self):
        assert normalize_whitespace("") == ""

    def test_none(self):
        assert normalize_whitespace(None) is None


class TestNormalizeWarningText:
    def test_removes_mid_word_hyphens(self):
        assert normalize_warning_text("ALCO-HOLIC") == "ALCOHOLIC"

    def test_removes_hyphen_with_space(self):
        assert normalize_warning_text("MACHIN- ERY") == "MACHINERY"

    def test_normalizes_space_after_numbered_marker(self):
        """'(1)According' should become '(1) According'."""
        assert normalize_warning_text("(1)According") == "(1) According"

    def test_normalizes_space_after_marker_2(self):
        """'(2)Consumption' should become '(2) Consumption'."""
        assert normalize_warning_text("(2)Consumption") == "(2) Consumption"

    def test_preserves_existing_space_after_marker(self):
        """Already correct '(1) According' should stay the same."""
        assert normalize_warning_text("(1) According") == "(1) According"

    def test_normalizes_space_before_marker(self):
        """'defects.(2)' should become 'defects. (2)'."""
        assert normalize_warning_text("defects.(2) Consumption") == "defects. (2) Consumption"


class TestExtractAbv:
    def test_percent_sign(self):
        assert extract_abv("40%") == 40.0

    def test_percent_with_space(self):
        assert extract_abv("40 %") == 40.0

    def test_abv_label(self):
        assert extract_abv("40% ABV") == 40.0

    def test_decimal(self):
        assert extract_abv("12.5%") == 12.5

    def test_plain_number(self):
        """COLA forms store just the number without % sign."""
        assert extract_abv("35") == 35.0

    def test_plain_decimal(self):
        assert extract_abv("11.5") == 11.5

    def test_plain_number_with_spaces(self):
        assert extract_abv("  50  ") == 50.0

    def test_none(self):
        assert extract_abv(None) is None

    def test_empty(self):
        assert extract_abv("") is None

    def test_non_numeric(self):
        assert extract_abv("no number here") is None

    def test_percent_preferred_over_plain(self):
        """When % is present, use it even if a plain number exists."""
        assert extract_abv("proof 80 40%") == 40.0


class TestExtractProof:
    def test_proof(self):
        assert extract_proof("80 Proof") == 80.0

    def test_lowercase(self):
        assert extract_proof("80 proof") == 80.0

    def test_none(self):
        assert extract_proof(None) is None


class TestNormalizeNetContents:
    def test_ml(self):
        assert normalize_net_contents("750 mL") == (750.0, "mL")

    def test_ml_uppercase(self):
        assert normalize_net_contents("750 ML") == (750.0, "mL")

    def test_fl_oz(self):
        assert normalize_net_contents("25.4 fl oz") == (25.4, "fl oz")

    def test_fl_oz_period(self):
        assert normalize_net_contents("25.4 fl. oz") == (25.4, "fl oz")

    def test_liter(self):
        assert normalize_net_contents("1 L") == (1000.0, "mL")

    def test_liter_spelled(self):
        assert normalize_net_contents("1 Liter") == (1000.0, "mL")

    def test_centiliter(self):
        assert normalize_net_contents("75 cL") == (750.0, "mL")

    def test_spelled_milliliters(self):
        """COLA forms use spelled-out 'MILLILITERS'."""
        assert normalize_net_contents("750 MILLILITERS") == (750.0, "mL")

    def test_spelled_milliliters_singular(self):
        assert normalize_net_contents("1 MILLILITER") == (1.0, "mL")

    def test_none(self):
        assert normalize_net_contents(None) == (None, None)

    def test_empty(self):
        assert normalize_net_contents("") == (None, None)

    def test_no_unit(self):
        assert normalize_net_contents("just text") == (None, None)


class TestNormalizeCountry:
    def test_known_alias(self):
        assert normalize_country("Italia") == "italy"

    def test_unknown_passthrough(self):
        assert normalize_country("Canada") == "Canada"

    def test_empty(self):
        assert normalize_country("") == ""


class TestNormalizeForFuzzy:
    def test_lowercase(self):
        assert normalize_for_fuzzy("HELLO") == "hello"

    def test_strips_punctuation(self):
        assert normalize_for_fuzzy("hello, world!") == "hello world"

    def test_folds_diacritics(self):
        assert normalize_for_fuzzy("Bärenjäger") == "barenjager"

    def test_empty(self):
        assert normalize_for_fuzzy("") == ""
