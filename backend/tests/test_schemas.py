"""Tests for Pydantic schema validation including new COLA fields."""

import pytest
from pydantic import ValidationError

from app.models.schemas import ApplicationData, FieldComparisonResult


class TestApplicationData:
    def test_minimal_valid(self):
        """Minimum required fields for ApplicationData."""
        data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 ML",
            beverage_type="distilled_spirits",
        )
        assert data.brand_name == "TEST"
        assert data.ttb_id is None
        assert data.fanciful_name is None
        assert data.source_of_product is None

    def test_full_cola_fields(self):
        """All COLA fields populated."""
        data = ApplicationData(
            ttb_id="11115001000373",
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES",
            alcohol_content="35",
            net_contents="750 MILLILITERS\n1 LITER",
            importer_name="SIDNEY FRANK IMPORTING CO.",
            beverage_type="distilled_spirits",
            source_of_product="imported",
        )
        assert data.ttb_id == "11115001000373"
        assert data.fanciful_name == "HONEY & BOURBON"
        assert data.source_of_product == "imported"

    def test_source_of_product_validation(self):
        """source_of_product must be 'domestic', 'imported', or None."""
        with pytest.raises(ValidationError):
            ApplicationData(
                brand_name="X",
                class_type="Y",
                alcohol_content="40",
                net_contents="750 ML",
                beverage_type="distilled_spirits",
                source_of_product="unknown",
            )

    def test_beverage_type_validation(self):
        """beverage_type must be beer, wine, or distilled_spirits."""
        with pytest.raises(ValidationError):
            ApplicationData(
                brand_name="X",
                class_type="Y",
                alcohol_content="40",
                net_contents="750 ML",
                beverage_type="cider",
            )

    def test_multiline_net_contents(self):
        """Net contents can be multi-line (from COLA forms)."""
        data = ApplicationData(
            brand_name="X",
            class_type="Y",
            alcohol_content="40",
            net_contents="375 MILLILITERS\n750 MILLILITERS\n1 LITER",
            beverage_type="distilled_spirits",
        )
        assert "\n" in data.net_contents
        assert len(data.net_contents.split("\n")) == 3


class TestFieldComparisonResult:
    def test_valid_statuses(self):
        for status in ["match", "content_mismatch", "field_missing", "extraction_uncertain"]:
            result = FieldComparisonResult(
                field_name="brand_name",
                status=status,
                confidence=50.0,
                match_strategy="fuzzy",
            )
            assert result.status == status
