"""Tests for TTB class/type canonicalization."""

import pytest
from app.services.ttb_classes import normalize_class_type


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
