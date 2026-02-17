"""Tests for TTB class/type canonicalization."""

import pytest
from app.services.ttb_classes import normalize_class_type, is_administrative_class_type


class TestNormalizeClassType:
    def test_vodka(self):
        canonical, _ = normalize_class_type("vodka", "distilled_spirits")
        assert canonical == "vodka"

    def test_vodka_uppercase(self):
        canonical, _ = normalize_class_type("VODKA", "distilled_spirits")
        assert canonical == "vodka"

    def test_gin(self):
        canonical, _ = normalize_class_type("Gin", "distilled_spirits")
        assert canonical == "gin"

    def test_tequila(self):
        canonical, _ = normalize_class_type("Tequila", "distilled_spirits")
        assert canonical == "tequila"

    def test_whisky_variant(self):
        """'Whisky' should normalize same as 'Whiskey'."""
        c1, _ = normalize_class_type("Whisky", "distilled_spirits")
        c2, _ = normalize_class_type("Whiskey", "distilled_spirits")
        assert c1 == c2

    def test_red_wine(self):
        canonical, _ = normalize_class_type("Red Wine", "wine")
        assert canonical == "red wine"

    def test_rose_wine_with_accent(self):
        """'Rosé Wine' (with diacritic) should match canonical 'rose wine'."""
        canonical, _ = normalize_class_type("Rosé Wine", "wine")
        assert canonical == "rose wine"

    def test_rose_wine_uppercase_accent(self):
        """'ROSÉ WINE' should match canonical 'rose wine'."""
        canonical, _ = normalize_class_type("ROSÉ WINE", "wine")
        assert canonical == "rose wine"

    def test_champagne(self):
        canonical, _ = normalize_class_type("Champagne", "wine")
        assert canonical == "champagne"

    def test_unknown_class(self):
        canonical, _ = normalize_class_type("COMPLETELY MADE UP CLASS", "distilled_spirits")
        assert canonical is None

    def test_qualifier_stripped(self):
        """Qualifiers like 'flavored' should be stripped."""
        canonical, qualifier = normalize_class_type(
            "Flavored Vodka", "distilled_spirits"
        )
        # Should still find vodka as base class
        assert canonical is not None

    def test_distilled_spirits_specialty(self):
        """Distilled spirits specialty is a recognized TTB class."""
        canonical, _ = normalize_class_type(
            "Distilled Spirits Specialty", "distilled_spirits"
        )
        assert canonical == "distilled spirits specialty"

    def test_brandy(self):
        canonical, _ = normalize_class_type("Brandy", "distilled_spirits")
        assert canonical is not None

    def test_rum(self):
        canonical, _ = normalize_class_type("Rum", "distilled_spirits")
        assert canonical is not None

    def test_beer(self):
        canonical, _ = normalize_class_type("Beer", "malt_beverages")
        assert canonical == "beer"

    def test_empty_string(self):
        canonical, _ = normalize_class_type("", "distilled_spirits")
        assert canonical is None


class TestIsAdministrativeClassType:
    """Tests for detecting administrative COLA codes that won't appear on labels."""

    def test_other_specialties(self):
        is_admin, base = is_administrative_class_type("OTHER SPECIALTIES & PROPRIETARIES")
        assert is_admin is True
        assert base is None

    def test_specialties_and_proprietaries(self):
        is_admin, base = is_administrative_class_type("SPECIALTIES & PROPRIETARIES")
        assert is_admin is True
        assert base is None

    def test_whisky_specialties(self):
        is_admin, base = is_administrative_class_type("WHISKY SPECIALTIES")
        assert is_admin is True
        assert base == "whisky"

    def test_vodka_specialties(self):
        is_admin, base = is_administrative_class_type("VODKA SPECIALTIES")
        assert is_admin is True
        assert base == "vodka"

    def test_gin_specialties(self):
        is_admin, base = is_administrative_class_type("GIN SPECIALTIES")
        assert is_admin is True
        assert base == "gin"

    def test_rum_specialties(self):
        is_admin, base = is_administrative_class_type("RUM SPECIALTIES")
        assert is_admin is True
        assert base == "rum"

    def test_whisky_proprietary(self):
        is_admin, base = is_administrative_class_type("WHISKY PROPRIETARY")
        assert is_admin is True
        assert base == "whisky"

    def test_malt_beverages_specialities_flavored(self):
        is_admin, base = is_administrative_class_type("MALT BEVERAGES SPECIALITIES - FLAVORED")
        assert is_admin is True
        assert base is None

    def test_malt_beverages_specialities(self):
        is_admin, base = is_administrative_class_type("MALT BEVERAGES SPECIALITIES")
        assert is_admin is True
        assert base is None

    def test_case_insensitive(self):
        is_admin, base = is_administrative_class_type("other specialties & proprietaries")
        assert is_admin is True

    def test_extra_whitespace(self):
        is_admin, base = is_administrative_class_type("  OTHER  SPECIALTIES &  PROPRIETARIES  ")
        assert is_admin is True

    def test_vodka_not_admin(self):
        """Regular TTB classes should NOT be flagged as administrative."""
        is_admin, base = is_administrative_class_type("VODKA")
        assert is_admin is False
        assert base is None

    def test_bourbon_whiskey_not_admin(self):
        is_admin, base = is_administrative_class_type("STRAIGHT BOURBON WHISKEY")
        assert is_admin is False

    def test_none_input(self):
        is_admin, base = is_administrative_class_type(None)
        assert is_admin is False

    def test_empty_string(self):
        is_admin, base = is_administrative_class_type("")
        assert is_admin is False

    # Fix #5: Pattern-based fallback for unlisted specialty codes
    def test_brandy_specialties_pattern(self):
        """Codes matching '<spirit> SPECIALTIES' pattern should be detected even if not hardcoded."""
        is_admin, base = is_administrative_class_type("BRANDY SPECIALTIES")
        assert is_admin is True
        assert base == "brandy"

    def test_tequila_specialties_pattern(self):
        is_admin, base = is_administrative_class_type("TEQUILA SPECIALTIES")
        assert is_admin is True
        assert base == "tequila"

    def test_brandy_proprietary_pattern(self):
        is_admin, base = is_administrative_class_type("BRANDY PROPRIETARY")
        assert is_admin is True
        assert base == "brandy"

    def test_pattern_does_not_match_plain_spirit(self):
        """'WHISKY' alone should not match the specialty pattern."""
        is_admin, _ = is_administrative_class_type("WHISKY")
        assert is_admin is False

    def test_pattern_does_not_match_arbitrary_text(self):
        is_admin, _ = is_administrative_class_type("RANDOM SPECIALTIES WORD")
        assert is_admin is False

    def test_other_cordials_liqueurs_is_admin(self):
        """'OTHER HERB & SEED CORDIALS/LIQUEURS' is an admin category code."""
        is_admin, base = is_administrative_class_type("OTHER HERB & SEED CORDIALS/LIQUEURS")
        assert is_admin is True

    def test_other_grape_brandy_is_admin(self):
        """'OTHER GRAPE BRANDY (PISCO, GRAPPA) FB' is an admin category code."""
        is_admin, base = is_administrative_class_type("OTHER GRAPE BRANDY (PISCO, GRAPPA) FB")
        assert is_admin is True

    def test_table_wine_is_not_admin(self):
        """'TABLE RED WINE' is a real class, not admin."""
        is_admin, _ = is_administrative_class_type("TABLE RED WINE")
        assert is_admin is False
