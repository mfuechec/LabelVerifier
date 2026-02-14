from app.services.normalizer import (
    normalize_whitespace,
    extract_abv,
    extract_proof,
    normalize_net_contents,
    normalize_for_fuzzy,
)


class TestWhitespaceNormalization:
    def test_collapse_multiple_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_trim_leading_trailing(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_line_breaks_to_space(self):
        assert normalize_whitespace("hello\nworld") == "hello world"

    def test_carriage_return_and_newline(self):
        assert normalize_whitespace("hello\r\nworld") == "hello world"

    def test_tabs_to_space(self):
        assert normalize_whitespace("hello\tworld") == "hello world"

    def test_mixed_whitespace(self):
        assert normalize_whitespace("  hello  \n\n  world  \t foo  ") == "hello world foo"

    def test_hyphenation_removal(self):
        """Labels often have hyphenated line breaks like BEV-\\nERAGES."""
        assert normalize_whitespace("BEV-\nERAGES") == "BEVERAGES"


class TestABVExtraction:
    def test_alc_vol_format(self):
        assert extract_abv("45% Alc./Vol.") == 45.0

    def test_abv_format(self):
        assert extract_abv("45% ABV") == 45.0

    def test_alcohol_by_volume(self):
        assert extract_abv("45% Alcohol by Volume") == 45.0

    def test_plain_percentage(self):
        assert extract_abv("45%") == 45.0

    def test_decimal_abv(self):
        assert extract_abv("43.3% Alc./Vol.") == 43.3

    def test_alc_vol_with_proof(self):
        assert extract_abv("45% Alc./Vol. (90 Proof)") == 45.0

    def test_none_input(self):
        assert extract_abv(None) is None

    def test_no_percentage(self):
        assert extract_abv("No alcohol here") is None


class TestProofExtraction:
    def test_standard_proof(self):
        assert extract_proof("90 Proof") == 90.0

    def test_proof_in_parentheses(self):
        assert extract_proof("45% Alc./Vol. (90 Proof)") == 90.0

    def test_decimal_proof(self):
        assert extract_proof("86.6 Proof") == 86.6

    def test_none_input(self):
        assert extract_proof(None) is None

    def test_no_proof(self):
        assert extract_proof("45% ABV") is None


class TestNetContentsNormalization:
    def test_ml_standard(self):
        val, unit = normalize_net_contents("750 mL")
        assert val == 750.0
        assert unit == "mL"

    def test_ml_no_space(self):
        val, unit = normalize_net_contents("750ML")
        assert val == 750.0
        assert unit == "mL"

    def test_ml_lowercase(self):
        val, unit = normalize_net_contents("750ml")
        assert val == 750.0
        assert unit == "mL"

    def test_cl_to_ml(self):
        val, unit = normalize_net_contents("75cL")
        assert val == 750.0
        assert unit == "mL"

    def test_liter(self):
        val, unit = normalize_net_contents("1L")
        assert val == 1000.0
        assert unit == "mL"

    def test_liter_decimal(self):
        val, unit = normalize_net_contents("1.75L")
        assert val == 1750.0
        assert unit == "mL"

    def test_fl_oz(self):
        val, unit = normalize_net_contents("25.4 fl oz")
        assert val == 25.4
        assert unit == "fl oz"

    def test_none_input(self):
        assert normalize_net_contents(None) == (None, None)


class TestFuzzyNormalization:
    def test_lowercase(self):
        assert normalize_for_fuzzy("HELLO WORLD") == "hello world"

    def test_strip_punctuation(self):
        result = normalize_for_fuzzy("Stone's Throw, Inc.")
        assert "'" not in result
        assert "," not in result
        assert "." not in result

    def test_collapse_spaces(self):
        assert "  " not in normalize_for_fuzzy("hello   world")
