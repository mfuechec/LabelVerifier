import pytest
from app.services.ttb_classes import normalize_class_type


class TestNormalizeClassTypeSpirits:
    def test_exact_canonical_class(self):
        canonical, qualifier = normalize_class_type("Bourbon Whiskey", "distilled_spirits")
        assert canonical == "bourbon whiskey"
        assert qualifier is None

    def test_strips_finishing_statement(self):
        canonical, qualifier = normalize_class_type(
            "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels",
            "distilled_spirits",
        )
        assert canonical == "straight bourbon whiskey"
        assert "finished in port wine barrels" in qualifier.lower()

    def test_strips_with_natural_flavors(self):
        canonical, qualifier = normalize_class_type(
            "Bourbon Whiskey with Natural Flavors",
            "distilled_spirits",
        )
        assert canonical == "bourbon whiskey"
        assert "natural flavors" in qualifier.lower()

    def test_strips_aged_in_statement(self):
        canonical, qualifier = normalize_class_type(
            "Rye Whiskey Aged in Charred Oak Barrels",
            "distilled_spirits",
        )
        assert canonical == "rye whiskey"
        assert "aged in" in qualifier.lower()

    def test_strips_barrel_rested(self):
        canonical, qualifier = normalize_class_type(
            "Vodka Barrel Rested",
            "distilled_spirits",
        )
        assert canonical == "vodka"
        assert "barrel rested" in qualifier.lower()

    def test_strips_locally_crafted(self):
        canonical, qualifier = normalize_class_type(
            "Locally Crafted Vodka",
            "distilled_spirits",
        )
        assert canonical == "vodka"
        assert "locally crafted" in qualifier.lower()

    def test_kentucky_geographic_qualifier(self):
        """Kentucky Straight Bourbon Whiskey should map to straight bourbon whiskey."""
        canonical, qualifier = normalize_class_type(
            "Kentucky Straight Bourbon Whiskey",
            "distilled_spirits",
        )
        assert canonical == "straight bourbon whiskey"

    def test_tennessee_geographic_qualifier(self):
        canonical, qualifier = normalize_class_type(
            "Tennessee Whiskey",
            "distilled_spirits",
        )
        assert canonical == "tennessee whiskey"

    def test_flavored_whiskey(self):
        canonical, qualifier = normalize_class_type(
            "Chocolate Flavored Whiskey",
            "distilled_spirits",
        )
        assert canonical == "flavored whiskey"

    def test_plain_vodka(self):
        canonical, qualifier = normalize_class_type("Vodka", "distilled_spirits")
        assert canonical == "vodka"
        assert qualifier is None

    def test_flavored_vodka(self):
        canonical, qualifier = normalize_class_type("Citrus Flavored Vodka", "distilled_spirits")
        assert canonical == "flavored vodka"

    def test_rum(self):
        canonical, qualifier = normalize_class_type("Rum", "distilled_spirits")
        assert canonical == "rum"

    def test_gin(self):
        canonical, qualifier = normalize_class_type("Gin", "distilled_spirits")
        assert canonical == "gin"

    def test_tequila(self):
        canonical, qualifier = normalize_class_type("Tequila", "distilled_spirits")
        assert canonical == "tequila"

    def test_brandy(self):
        canonical, qualifier = normalize_class_type("Brandy", "distilled_spirits")
        assert canonical == "brandy"

    def test_straight_rye_whiskey(self):
        canonical, qualifier = normalize_class_type("Straight Rye Whiskey", "distilled_spirits")
        assert canonical == "straight rye whiskey"

    def test_whisky_variant_spelling(self):
        canonical, qualifier = normalize_class_type("Bourbon Whisky", "distilled_spirits")
        assert canonical == "bourbon whiskey"

    def test_case_insensitive(self):
        canonical, qualifier = normalize_class_type("STRAIGHT BOURBON WHISKEY", "distilled_spirits")
        assert canonical == "straight bourbon whiskey"

    def test_corn_whiskey(self):
        canonical, qualifier = normalize_class_type("Corn Whiskey", "distilled_spirits")
        assert canonical == "corn whiskey"

    def test_blended_whiskey(self):
        canonical, qualifier = normalize_class_type("Blended Whiskey", "distilled_spirits")
        assert canonical == "blended whiskey"

    def test_london_dry_gin(self):
        canonical, qualifier = normalize_class_type("London Dry Gin", "distilled_spirits")
        assert canonical == "london dry gin"

    def test_scotch_whisky(self):
        canonical, qualifier = normalize_class_type("Scotch Whisky", "distilled_spirits")
        assert canonical == "scotch whisky"


class TestNormalizeClassTypeWine:
    def test_red_wine(self):
        canonical, qualifier = normalize_class_type("Red Wine", "wine")
        assert canonical == "red wine"

    def test_white_wine(self):
        canonical, qualifier = normalize_class_type("White Wine", "wine")
        assert canonical == "white wine"

    def test_rose_wine(self):
        canonical, qualifier = normalize_class_type("Rose Wine", "wine")
        assert canonical == "rose wine"

    def test_sparkling_wine(self):
        canonical, qualifier = normalize_class_type("Sparkling Wine", "wine")
        assert canonical == "sparkling wine"

    def test_table_wine(self):
        canonical, qualifier = normalize_class_type("Table Wine", "wine")
        assert canonical == "table wine"

    def test_dessert_wine(self):
        canonical, qualifier = normalize_class_type("Dessert Wine", "wine")
        assert canonical == "dessert wine"

    def test_wine_with_appellation(self):
        """Wine with geographic appellation -- qualifier stripped, base class matched."""
        canonical, qualifier = normalize_class_type(
            "Red Wine from Napa Valley",
            "wine",
        )
        assert canonical == "red wine"


class TestNormalizeClassTypeBeer:
    def test_beer(self):
        canonical, qualifier = normalize_class_type("Beer", "malt_beverages")
        assert canonical == "beer"

    def test_ale(self):
        canonical, qualifier = normalize_class_type("Ale", "malt_beverages")
        assert canonical == "ale"

    def test_lager(self):
        canonical, qualifier = normalize_class_type("Lager", "malt_beverages")
        assert canonical == "lager"

    def test_stout(self):
        canonical, qualifier = normalize_class_type("Stout", "malt_beverages")
        assert canonical == "stout"

    def test_malt_beverage(self):
        canonical, qualifier = normalize_class_type("Malt Beverage", "malt_beverages")
        assert canonical == "malt beverage"


class TestNormalizeClassTypeUnknown:
    def test_unknown_class_returns_none(self):
        canonical, qualifier = normalize_class_type("Xyzzy Drink", "distilled_spirits")
        assert canonical is None

    def test_none_input(self):
        canonical, qualifier = normalize_class_type(None, "distilled_spirits")
        assert canonical is None
        assert qualifier is None

    def test_empty_input(self):
        canonical, qualifier = normalize_class_type("", "distilled_spirits")
        assert canonical is None
        assert qualifier is None

    def test_whitespace_only(self):
        canonical, qualifier = normalize_class_type("   ", "distilled_spirits")
        assert canonical is None
        assert qualifier is None


class TestNormalizeClassTypeQualifierCombinations:
    def test_multiple_qualifiers_stripped(self):
        canonical, qualifier = normalize_class_type(
            "Small Batch Bourbon Whiskey Finished in Sherry Casks with Honey",
            "distilled_spirits",
        )
        assert canonical == "bourbon whiskey"
        assert qualifier is not None

    def test_infused_with_stripped(self):
        canonical, qualifier = normalize_class_type(
            "Vodka Infused with Natural Flavors",
            "distilled_spirits",
        )
        assert canonical == "vodka"
        assert "infused" in qualifier.lower()
