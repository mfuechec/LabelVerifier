"""
Integration tests that exercise the full pipeline:
  extraction (mocked) -> merger -> comparison -> compliance -> scoring

Uses fixtures from sample_applications.json with realistic mock extraction
results. All services except extraction are real (no mocks).

Scenario categories:
  - pass: application matches label exactly
  - fail_mismatch: application has intentionally wrong values vs label
  - fail_missing: label missing required fields
  - needs_review: hard-to-read labels with extraction uncertainty
  - edge_cases: warning variations, non-English text, etc.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.schemas import ApplicationData, FieldComparisonResult
from app.services.extraction import ExtractionResult
from app.services.comparison import ComparisonService, ConfidenceScorer, CANONICAL_WARNING
from app.services.compliance import ComplianceChecker
from app.services.merger import ImageMerger

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sample_applications.json"


def load_fixtures():
    with open(FIXTURES_PATH) as f:
        return json.load(f)["fixtures"]


FIXTURES = load_fixtures()


def get_fixture(fixture_id: str) -> dict:
    for f in FIXTURES:
        if f["id"] == fixture_id:
            return f
    raise ValueError(f"Fixture {fixture_id} not found")


def fixtures_by_category(category: str) -> list[dict]:
    return [f for f in FIXTURES if f["scenario_category"] == category]


def build_app_data(fixture: dict) -> ApplicationData:
    """Build ApplicationData from fixture's application_data."""
    ad = fixture["application_data"]
    return ApplicationData(
        application_id=ad.get("application_id"),
        brand_name=ad["brand_name"],
        class_type=ad["class_type"],
        alcohol_content=ad["alcohol_content"],
        net_contents=ad["net_contents"],
        producer_name=ad.get("producer_name"),
        producer_address=ad.get("producer_address"),
        country_of_origin=ad.get("country_of_origin"),
        importer_name=ad.get("importer_name"),
        importer_address=ad.get("importer_address"),
        beverage_type=ad["beverage_type"],
        has_sulfites_declaration=ad.get("has_sulfites_declaration", False),
    )


# =============================================================================
# Mock extraction data
# =============================================================================
# These represent what Claude vision would extract from the actual label images.
# For 'good' labels the extracted values closely match what's on the label.
# For 'bad' labels the extracted values reflect the actual label content.

MOCK_EXTRACTIONS = {
    # --- Pass fixtures: extraction matches label, which matches app ---
    "pass-angels-envy": {
        "brand_name": "Angel's Envy",
        "class_type": "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels",
        "alcohol_content": "43.3% Alc./Vol. (86.6 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Louisville Spirits Group",
        "producer_address": "Louisville, Kentucky",
        "government_warning": CANONICAL_WARNING,
    },
    "pass-den-of-thieves": {
        "brand_name": "Den of Thieves",
        "class_type": "Chocolate Flavored Whiskey",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Strong Spirits",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },
    # hanami-gin moved to edge_cases (miniature bottle, importer not visible, warning punctuation)
    "edge-hanami-gin-miniature": {
        "brand_name": "Hanami",
        "class_type": "Dry Gin",
        "alcohol_content": "43% Alc./Vol. (86 Proof)",
        "net_contents": "50 mL",
        "producer_name": "P. Melchers Distilleries BV",
        "producer_address": "Lelystad, The Netherlands",
        "country_of_origin": "Holland",
        "government_warning": CANONICAL_WARNING.replace("WARNING:", "WARNING"),
    },
    # rosso-veneto moved to needs_review (brand confusion, Italian text)
    "review-rosso-veneto-brand-confusion": {
        "brand_name": "DUO",
        "class_type": "Rosso Veneto",
        "alcohol_content": "14.5%",
        "net_contents": "750 mL",
        "country_of_origin": "Italia",
        "importer_name": "Marcato Direct",
        "importer_address": "Addison, IL 60108",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING.replace("WARNING:", "WARNING:").rstrip() + "",
    },
    "pass-black-maple-hill": {
        "brand_name": "Black Maple Hill",
        "class_type": "Oregon Straight Rye Whiskey",
        "alcohol_content": "47.5% Alc./Vol. (95 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Stein Distillery",
        "producer_address": "Joseph, Oregon",
        "government_warning": CANONICAL_WARNING,
    },
    "pass-fuel-moonshine": {
        "brand_name": "Fuel",
        "class_type": "Grain Neutral Spirits with Natural Flavor Added",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Redline Beverage",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },
    # market-alley moved to edge_cases (gov warning missing colon)
    "edge-market-alley-warning-punct": {
        "brand_name": "Market Alley",
        "class_type": "Barrel Rested Gin",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Thistle Finch Distilling LLC",
        "producer_address": "Lancaster, PA",
        "government_warning": CANONICAL_WARNING.replace("WARNING:", "WARNING"),
    },
    # misunderstood moved to needs_review (gov warning word difference)
    "review-misunderstood-warning": {
        "brand_name": "Misunderstood",
        "class_type": "Ginger Spiced Whiskey",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Misunderstood Whiskey",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING.replace("your ability", "the ability"),
    },
    # cascade-val moved to edge_cases (only front image, no gov warning)
    "edge-cascade-val-no-back": {
        "brand_name": "Cascade",
        "class_type": "Red Wine",
        "alcohol_content": "11.5%",
        "net_contents": "750 mL",
        "producer_name": "Cascade Winery",
        "producer_address": "Grand Rapids, MI",
        "sulfites_declaration": "Contains Sulfites",
    },
    # lenz-moser moved to needs_review (class mismatch, importer uncertain)
    "review-lenz-moser-class-extraction": {
        "brand_name": "Lenz Moser",
        "class_type": "Grüner Veltliner",
        "alcohol_content": "12%",
        "net_contents": "1.0 L",
        "country_of_origin": "Austria",
        "importer_name": "Nich W&S",
        "importer_address": "Cedar Knolls, NJ",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING,
    },

    # --- Mismatch fixtures: extraction matches label, but app has wrong values ---
    # The extraction is the SAME as the corresponding pass fixture (same label)
    "mismatch-angels-envy-wrong-abv": {
        "brand_name": "Angel's Envy",
        "class_type": "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels",
        "alcohol_content": "43.3% Alc./Vol. (86.6 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Louisville Spirits Group",
        "producer_address": "Louisville, Kentucky",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-den-of-thieves-wrong-brand": {
        "brand_name": "Den of Thieves",
        "class_type": "Chocolate Flavored Whiskey",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Strong Spirits",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-hanami-wrong-class": {
        "brand_name": "Hanami",
        "class_type": "Dry Gin",
        "alcohol_content": "43% Alc./Vol. (86 Proof)",
        "net_contents": "750 mL",
        "producer_name": "P. Melchers Distilleries BV",
        "producer_address": "Lelystad, The Netherlands",
        "country_of_origin": "Holland",
        "importer_name": "The Red Sea Import Company",
        "importer_address": "Princeton, MN",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-black-maple-hill-wrong-net": {
        "brand_name": "Black Maple Hill",
        "class_type": "Oregon Straight Rye Whiskey",
        "alcohol_content": "47.5% Alc./Vol. (95 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Stein Distillery",
        "producer_address": "Joseph, Oregon",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-fuel-wrong-producer": {
        "brand_name": "Fuel",
        "class_type": "Grain Neutral Spirits with Natural Flavor Added",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Redline Beverage",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-market-alley-wrong-abv": {
        "brand_name": "Market Alley",
        "class_type": "Barrel Rested Gin",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Thistle Finch Distilling LLC",
        "producer_address": "Lancaster, PA",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-mckenzie-wrong-class": {
        "brand_name": "McKenzie Brew House",
        "class_type": "Locally Crafted Vodka",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "1 L",
        "producer_name": "Kiki Vodka Company LLC",
        "producer_address": "Hatfield, PA",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-misunderstood-wrong-brand": {
        "brand_name": "Misunderstood",
        "class_type": "Ginger Spiced Whiskey",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Misunderstood Whiskey",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-rosso-veneto-wrong-abv": {
        "brand_name": "Rosso Veneto",
        "class_type": "Red Wine",
        "alcohol_content": "14.5%",
        "net_contents": "750 mL",
        "country_of_origin": "Italy",
        "importer_name": "Marcato Direct",
        "importer_address": "Addison, IL 60108",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-cascade-wrong-origin": {
        "brand_name": "Cascade",
        "class_type": "Red Wine",
        "alcohol_content": "11.5%",
        "net_contents": "750 mL",
        "producer_name": "Cascade Winery",
        "producer_address": "Grand Rapids, MI",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-lenz-moser-wrong-importer": {
        "brand_name": "Lenz Moser",
        "class_type": "Dry White Wine",
        "alcohol_content": "12%",
        "net_contents": "1.0 L",
        "country_of_origin": "Austria",
        "importer_name": "Niche Import Co.",
        "importer_address": "Cedar Knolls, NJ",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING,
    },
    "mismatch-gordian-knot-wrong-contents": {
        "brand_name": "Gordian Knot",
        "class_type": "Aged Rum",
        "alcohol_content": "42% Alc./Vol. (84 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Nicks and Bruce",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },

    # --- Missing fixtures: label has actual deficiencies ---
    "missing-collabor-and-tion": {
        "brand_name": "Collabor&tion",
        "class_type": "Straight Bourbon Whiskey Finished in Brandy Barrels",
        "alcohol_content": "60% Alc./Vol. (120 Proof)",
        "net_contents": "750 mL",
        # No government_warning -- missing from label (no back panel)
    },
    "missing-cotton-hollow": {
        "brand_name": "Cotton Hollow",
        "class_type": "Straight Bourbon Whiskey",
        "alcohol_content": "46.5% Alc./Vol. (93 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Cotton Hollow Distillery",
        "producer_address": "Indiana",
        # No government_warning -- missing from label
    },
    "missing-resilient": {
        "brand_name": "Resilient",
        "class_type": "Straight Bourbon Whisky",  # Note: Whisky not Whiskey
        "alcohol_content": "53.5% Alc./Vol. (107 Proof)",
        "net_contents": "750 mL",
        # No government_warning -- missing from label
    },
    "missing-warm": {
        "brand_name": "Warm",
        "class_type": "Bourbon Whiskey",
        "alcohol_content": "48% Alc./Vol. (96 Proof)",
        "net_contents": "750 mL",
        # No government_warning -- tiny rotated text not extractable
    },
    "missing-barrilito": {
        "brand_name": "Barrilito",
        "class_type": "Cerveza",  # Spanish, not "Beer"
        "alcohol_content": "3.6%",
        "net_contents": "1 QT 8 FL.OZ.",
        "producer_name": "Cerveceria Moctezuma",
        "producer_address": "Monterrey, Mexico",
        "country_of_origin": "Mexico",
        "importer_name": "Labatt USA Operating Co. LLC",
        "importer_address": "Norwalk, CT",
        "government_warning": CANONICAL_WARNING,
    },
    "missing-forte-masso": {
        "brand_name": "Forte Masso",
        "class_type": "Red Wine",
        "alcohol_content": "13.5%",
        "net_contents": "750 mL",
        "country_of_origin": "Italy",
        "importer_name": "Vino Italiano Distributors LLC",  # Different from app
        "importer_address": "San Rafael, CA 94901",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": CANONICAL_WARNING,
    },

    # --- Needs review: extraction uncertain due to image quality ---
    "review-mokka": {
        "brand_name": None,  # Stylized font -- extraction fails
        "class_type": None,  # Stylized font -- extraction fails
        "alcohol_content": "35%",
        "net_contents": "750 mL",
        "government_warning": CANONICAL_WARNING,
    },
    "review-alpine-lafayette": {
        "brand_name": None,  # Damask background obscures
        "class_type": None,  # Damask background obscures
        "alcohol_content": "40%",
        "net_contents": "750 mL",
        "producer_name": "Alpine Distilling",
        "producer_address": "Park City, UT",
        "government_warning": CANONICAL_WARNING,
    },
    "review-howling-moon": {
        "brand_name": None,  # White text on dark photo
        "class_type": None,  # White text on dark photo
        "alcohol_content": "40%",
        "net_contents": "750 mL",
        "producer_name": "Howling Moon",
        "producer_address": "Asheville, North Carolina",
        "government_warning": CANONICAL_WARNING,
    },
    "review-rocky-mount": {
        "brand_name": None,  # Cursive script throughout
        "class_type": None,  # Cursive script throughout
        "alcohol_content": "50%",
        "net_contents": "750 mL",
        "producer_name": None,  # Also hard to read
        "government_warning": CANONICAL_WARNING,
    },
    "review-sailor-jerry": {
        "brand_name": None,  # Tattoo art on miniature label
        "class_type": None,  # Tattoo art on miniature label
        "alcohol_content": "46%",
        "net_contents": "50 mL",
        "government_warning": None,  # Extremely small, not extractable
    },
    "review-salted-caramel": {
        "brand_name": None,  # Caramel graphic obscures brand
        "class_type": None,  # Caramel graphic obscures class
        "alcohol_content": "35%",
        "net_contents": "750 mL",
        "producer_name": "Redline Beverage",
        "producer_address": "Bardstown, KY",
        "government_warning": CANONICAL_WARNING,
    },

    # --- Edge cases: warning variations, non-English text, etc. ---
    "edge-woodford-warning-omission": {
        "brand_name": "Woodford Reserve",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45.2% Alc./Vol. (90.4 Proof)",
        "net_contents": "750 mL",
        "producer_name": "The Woodford Reserve Distillery",
        "producer_address": "Versailles, KY",
        "government_warning": (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages because of the risk "
            "of birth defects. (2) Consumption of alcoholic beverages impairs "
            "your ability to drive a car or operate machinery, and may cause "
            "health problems."
        ),
    },
    "edge-fete-warning-hyphenation": {
        "brand_name": "Fete",
        "class_type": "Rose Wine",
        "alcohol_content": "12.5%",
        "net_contents": "750 mL",
        "country_of_origin": "France",
        "sulfites_declaration": "Contains Sulfites",
        "government_warning": (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery "
            "and may cause health problems."
        ),
    },
    "edge-barenjager-typo-warning": {
        "brand_name": "Barenjager",
        "class_type": "Honey Liqueur",
        "alcohol_content": "35% Alc./Vol. (70 Proof)",
        "net_contents": "50 mL",
        "producer_name": "Schwarze und Schlichte GmbH",
        "producer_address": "Oelde, Germany",
        "country_of_origin": "Germany",
        "importer_name": "Sidney Frank Importing Co., Inc.",
        "importer_address": "New Rochelle, NY",
        "government_warning": (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Comsumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery, "
            "and may cause health problems."
        ),
    },
    "edge-seven-fathoms-warning-space": {
        "brand_name": "Seven Fathoms",
        "class_type": "Cayman Islands Premium Rum",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Cayman Spirits Co.",
        "producer_address": "Grand Cayman, Cayman Islands",
        "country_of_origin": "Cayman Islands",
        "government_warning": (
            "GOVERNMENT WARNING : (1) According to the Surgeon General, "
            "women should not drink alcoholic beverages during pregnancy "
            "because of the risk of birth defects. (2) Consumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery, "
            "and may cause health problems."
        ),
    },
    "edge-monkey-47-german-class": {
        "brand_name": "Monkey 47",
        "class_type": "Schwarzwald Dry Gin",
        "alcohol_content": "47% Alc./Vol. (94 Proof)",
        "net_contents": "375 mL",
        "producer_name": "Black Forest Distillers",
        "producer_address": "Lossburg, Germany",
        "country_of_origin": "Germany",
        "importer_name": "Sidney Frank Importing Co., Inc.",
        "importer_address": "New Rochelle, NY",
        "government_warning": CANONICAL_WARNING,
    },
    "edge-casamigos-spanish-class": {
        "brand_name": "Casamigos",
        "class_type": "Licor de Agave Joven",  # Spanish class/type from front label
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name": "Productos Finos de Agave",
        "producer_address": "Jalisco, Mexico",
        "country_of_origin": "Mexico",
        "importer_name": "Casamigos Spirits Company",
        "importer_address": "New York, NY",
        "government_warning": CANONICAL_WARNING,
    },
}


def build_mock_extraction(fixture_id: str) -> dict[str, str | None]:
    """Get mock extraction data for a fixture."""
    return MOCK_EXTRACTIONS.get(fixture_id, {})


# Extraction confidence overrides for fixtures with uncertain extraction.
# Fields marked "medium" that produce content_mismatch become extraction_uncertain.
MOCK_EXTRACTION_CONFIDENCES: dict[str, dict[str, str]] = {
    "review-rosso-veneto-brand-confusion": {
        "brand_name": "medium",
        "class_type": "medium",
        "country_of_origin": "medium",
    },
    "review-misunderstood-warning": {
        "government_warning": "medium",
    },
    "review-lenz-moser-class-extraction": {
        "importer_name": "medium",
    },
}

# --- Real service instances (no mocks) ---
comparison_service = ComparisonService()
confidence_scorer = ConfidenceScorer()
compliance_checker = ComplianceChecker()
merger = ImageMerger()


def run_pipeline(fixture_id: str) -> tuple[list[FieldComparisonResult], float, str]:
    """Run the full comparison+scoring pipeline for a fixture.

    Returns (field_results, overall_confidence, status).
    """
    fixture = get_fixture(fixture_id)
    app_data = build_app_data(fixture)
    extracted = build_mock_extraction(fixture_id)
    extraction_confidences = MOCK_EXTRACTION_CONFIDENCES.get(fixture_id)

    field_results = comparison_service.compare_fields(
        extracted, app_data, app_data.beverage_type,
        extraction_confidences=extraction_confidences,
    )

    overall_confidence, status = confidence_scorer.calculate(field_results)

    return field_results, overall_confidence, status


def get_field_status(fields: list[FieldComparisonResult], field_name: str) -> str | None:
    """Get the status of a specific field from results."""
    for f in fields:
        if f.field_name == field_name:
            return f.status
    return None


def get_field_confidence(fields: list[FieldComparisonResult], field_name: str) -> float | None:
    """Get the confidence of a specific field from results."""
    for f in fields:
        if f.field_name == field_name:
            return f.confidence
    return None


# ============================================================
# Pass scenarios: application matches label exactly
# ============================================================
PASS_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "pass"]


class TestPassScenarios:
    """All pass scenarios should result in status='pass' with high confidence."""

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_overall_status_is_pass(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        assert status == "pass", f"{fixture_id}: expected pass, got {status}"

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_confidence_at_least_90(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        assert confidence >= 90.0, f"{fixture_id}: confidence {confidence} < 90"

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_no_content_mismatches(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        mismatches = [f for f in fields if f.status == "content_mismatch"]
        assert len(mismatches) == 0, (
            f"{fixture_id}: unexpected mismatches: "
            f"{[(m.field_name, m.status) for m in mismatches]}"
        )

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Fail mismatch scenarios: app has wrong values vs label
# ============================================================
MISMATCH_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "fail_mismatch"]


class TestMismatchScenarios:
    """Mismatch scenarios should fail or need review (non-critical fields → needs_review)."""

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_overall_status_matches_expected(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_has_at_least_one_mismatch(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        expected_mismatches = [
            k for k, v in fixture["expected_outcome"]["expected_field_results"].items()
            if v == "content_mismatch"
        ]
        actual_mismatches = [f.field_name for f in fields if f.status == "content_mismatch"]
        for expected_field in expected_mismatches:
            assert expected_field in actual_mismatches, (
                f"{fixture_id}: expected {expected_field} to be content_mismatch, "
                f"actual mismatches: {actual_mismatches}"
            )

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_matching_fields_still_match(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            if expected == "match":
                actual = get_field_status(fields, field_name)
                assert actual == "match", (
                    f"{fixture_id}.{field_name}: expected match, got {actual}"
                )


# ============================================================
# Fail missing scenarios: label missing required fields
# ============================================================
MISSING_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "fail_missing"]


class TestMissingScenarios:
    """Labels with missing or mismatched fields should fail or need review."""

    @pytest.mark.parametrize("fixture_id", MISSING_IDS)
    def test_overall_status_matches_expected(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", MISSING_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Needs review scenarios: extraction uncertainty
# ============================================================
REVIEW_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "needs_review"]


class TestNeedsReviewScenarios:
    """Hard-to-read labels should fail or need review."""

    @pytest.mark.parametrize("fixture_id", REVIEW_IDS)
    def test_overall_status_is_fail_or_needs_review(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        # Missing fields cause fail (which is correct -- agent must review)
        assert status in ("fail", "needs_review"), (
            f"{fixture_id}: expected fail/needs_review, got {status}"
        )

    @pytest.mark.parametrize("fixture_id", REVIEW_IDS)
    def test_has_missing_or_uncertain_fields(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        problem_fields = [
            f for f in fields
            if f.status in ("field_missing", "extraction_uncertain")
        ]
        assert len(problem_fields) > 0, (
            f"{fixture_id}: expected at least one missing/uncertain field"
        )


# ============================================================
# Edge case scenarios: warning variations, non-English text
# ============================================================
EDGE_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "edge_cases"]


class TestEdgeCaseScenarios:
    """Edge cases should produce expected outcomes."""

    @pytest.mark.parametrize("fixture_id", EDGE_IDS)
    def test_overall_status_is_fail(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", EDGE_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Specific representative tests for key scenarios
# ============================================================
class TestAngelsEnvyPass:
    """Representative pass test with detailed assertions."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline("pass-angels-envy")

    def test_overall_pass(self):
        assert self.status == "pass"
        assert self.confidence >= 90.0

    def test_no_mismatches_or_missing(self):
        for f in self.fields:
            assert f.status not in ("content_mismatch", "field_missing"), (
                f"{f.field_name} has unexpected status {f.status}"
            )


class TestAngelsEnvyWrongAbv:
    """Representative mismatch test: ABV differs between app and label."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "mismatch-angels-envy-wrong-abv"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_abv_is_content_mismatch(self):
        assert get_field_status(self.fields, "alcohol_content") == "content_mismatch"

    def test_other_fields_still_match(self):
        assert get_field_status(self.fields, "brand_name") == "match"
        assert get_field_status(self.fields, "class_type") == "match"
        assert get_field_status(self.fields, "net_contents") == "match"
        assert get_field_status(self.fields, "government_warning") == "match"


class TestMokkaExtractionUncertain:
    """Representative needs_review test: stylized fonts prevent extraction."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline("review-mokka")

    def test_overall_fail_or_needs_review(self):
        assert self.status in ("fail", "needs_review")

    def test_brand_missing(self):
        assert get_field_status(self.fields, "brand_name") == "field_missing"

    def test_class_missing(self):
        assert get_field_status(self.fields, "class_type") == "field_missing"

    def test_simple_fields_still_match(self):
        assert get_field_status(self.fields, "alcohol_content") == "match"
        assert get_field_status(self.fields, "net_contents") == "match"


class TestWoodfordWarningOmission:
    """Representative edge case: warning text missing 'during pregnancy'."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-woodford-warning-omission"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_warning_is_content_mismatch(self):
        assert get_field_status(self.fields, "government_warning") == "content_mismatch"

    def test_other_fields_match(self):
        assert get_field_status(self.fields, "brand_name") == "match"
        assert get_field_status(self.fields, "class_type") == "match"
        assert get_field_status(self.fields, "alcohol_content") == "match"


# ============================================================
# Compliance checker integration
# ============================================================
class TestComplianceIntegration:
    """Verify compliance checker works with real extraction data."""

    def test_good_spirits_no_issues(self):
        extracted = build_mock_extraction("pass-angels-envy")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=False
        )
        assert len(issues) == 0

    def test_imported_spirits_no_issues(self):
        extracted = build_mock_extraction("edge-hanami-gin-miniature")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        assert len(issues) == 0

    def test_imported_wine_sulfites_not_flagged(self):
        extracted = build_mock_extraction("review-rosso-veneto-brand-confusion")
        issues = compliance_checker.check_compliance(
            extracted, "wine", is_imported=True, requires_sulfites=True
        )
        flagged = [i.field_name for i in issues]
        assert "sulfites_declaration" not in flagged
        assert "country_of_origin" not in flagged

    def test_mokka_missing_fields_flagged(self):
        extracted = build_mock_extraction("review-mokka")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=False
        )
        missing_fields = [i.field_name for i in issues]
        assert "brand_name" in missing_fields
        assert "class_type" in missing_fields
        assert "producer_name" in missing_fields


# ============================================================
# Merger integration with multi-panel extraction
# ============================================================
class TestMergerIntegration:
    """Verify merger correctly combines front+back panels."""

    def test_merge_front_back_no_conflict(self):
        front = {
            "brand_name": {"value": "Angel's Envy", "confidence": 95.0},
            "class_type": {"value": "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels", "confidence": 90.0},
            "alcohol_content": {"value": "43.3% Alc./Vol.", "confidence": 92.0},
            "net_contents": {"value": "750 mL", "confidence": 98.0},
        }
        back = {
            "producer_name": {"value": "Louisville Spirits Group", "confidence": 90.0},
            "government_warning": {"value": CANONICAL_WARNING, "confidence": 85.0},
        }
        merged = merger.merge_panels({"front": front, "back": back})
        assert "brand_name" in merged.fields
        assert "government_warning" in merged.fields
        assert merged.fields["brand_name"].source_panel == "front"
        assert merged.fields["government_warning"].source_panel == "back"
        assert len(merged.conflicts) == 0

    def test_merge_conflict_prefers_front(self):
        front = {
            "brand_name": {"value": "Angel's Envy", "confidence": 90.0},
        }
        back = {
            "brand_name": {"value": "ANGEL'S ENVY", "confidence": 85.0},
        }
        merged = merger.merge_panels({"front": front, "back": back})
        assert merged.fields["brand_name"].value == "Angel's Envy"
        assert merged.fields["brand_name"].source_panel == "front"
        assert len(merged.conflicts) == 1


# ============================================================
# End-to-end pipeline with orchestrator (mocked extraction)
# ============================================================
class TestOrchestratorIntegration:
    """Test the orchestrator with mocked extraction but real everything else."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        from app.db.setup import create_tables, get_db
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        from app.services.orchestrator import VerificationOrchestrator
        orch = VerificationOrchestrator(db_path=tmp_db)
        return orch

    def _mock_extraction_result(self, fixture_id: str, panel: str) -> ExtractionResult:
        """Build an ExtractionResult that mimics Claude's output format."""
        raw = build_mock_extraction(fixture_id)
        fields = {}
        for field_name, value in raw.items():
            fields[field_name] = {
                "value": value,
                "bounding_box": {"x": 10, "y": 10, "width": 30, "height": 5} if value else None,
            }
        return ExtractionResult(
            fields=fields,
            panel_type=panel,
            extraction_notes="Mock extraction for testing",
        )

    @pytest.mark.asyncio
    async def test_pass_scenario_full_orchestrator(self, orchestrator):
        fixture = get_fixture("pass-angels-envy")
        app_data = build_app_data(fixture)

        mock_front = self._mock_extraction_result("pass-angels-envy", "front")
        mock_back = self._mock_extraction_result("pass-angels-envy", "back")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_front if panel_type == "front" else mock_back

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front", b"fake-back"],
                panels=["front", "back"],
                application_data=app_data,
            )

        assert result.status == "pass"
        assert result.overall_confidence >= 90.0
        assert result.session_id is not None
        assert result.beverage_type == "distilled_spirits"

    @pytest.mark.asyncio
    async def test_mismatch_scenario_full_orchestrator(self, orchestrator):
        fixture = get_fixture("mismatch-angels-envy-wrong-abv")
        app_data = build_app_data(fixture)

        mock_result = self._mock_extraction_result("mismatch-angels-envy-wrong-abv", "front")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_result

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front"],
                panels=["front"],
                application_data=app_data,
            )

        assert result.status == "fail"
        abv_field = next(f for f in result.fields if f.field_name == "alcohol_content")
        assert abv_field.status == "content_mismatch"

    @pytest.mark.asyncio
    async def test_result_persisted_to_db(self, orchestrator, tmp_db):
        fixture = get_fixture("pass-den-of-thieves")
        app_data = build_app_data(fixture)

        mock_result = self._mock_extraction_result("pass-den-of-thieves", "front")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_result

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front"],
                panels=["front"],
                application_data=app_data,
            )

        from app.db.setup import get_db
        conn = get_db(tmp_db)
        try:
            row = conn.execute(
                "SELECT * FROM verification_sessions WHERE id = ?",
                (result.session_id,),
            ).fetchone()
            assert row is not None
            assert row["status"] == "pass"
            assert row["beverage_type"] == "distilled_spirits"

            fields = conn.execute(
                "SELECT * FROM comparison_results WHERE session_id = ?",
                (result.session_id,),
            ).fetchall()
            assert len(fields) > 0
        finally:
            conn.close()
