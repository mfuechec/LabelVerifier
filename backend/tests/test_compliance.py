"""Tests for TTB mandatory field compliance checking."""

import pytest
from app.services.compliance import ComplianceChecker


@pytest.fixture
def checker():
    return ComplianceChecker()


class TestSpiritsMandatoryFields:
    """Spirits require: brand, class, ABV, net contents, producer, gov warning."""

    def test_all_present_no_issues(self, checker):
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": "Other Specialties",
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "producer_name": "Howling Moon LLC",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(extracted, "distilled_spirits")
        assert len(issues) == 0

    def test_missing_brand(self, checker):
        extracted = {
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Test",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(extracted, "distilled_spirits")
        field_names = [i.field_name for i in issues]
        assert "brand_name" in field_names

    def test_missing_warning(self, checker):
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Test",
        }
        issues = checker.check_compliance(extracted, "distilled_spirits")
        field_names = [i.field_name for i in issues]
        assert "government_warning" in field_names

    def test_missing_abv(self, checker):
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "net_contents": "750 mL",
            "producer_name": "Test",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(extracted, "distilled_spirits")
        field_names = [i.field_name for i in issues]
        assert "alcohol_content" in field_names


class TestWineMandatoryFields:
    def test_wine_sulfites_required(self, checker):
        """Wine with sulfites flag should have declaration on label."""
        extracted = {
            "brand_name": "CASCADE",
            "class_type": "Table Red Wine",
            "alcohol_content": "12%",
            "net_contents": "750 mL",
            "producer_name": "Cascade Winery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(
            extracted, "wine", requires_sulfites=True
        )
        field_names = [i.field_name for i in issues]
        assert "sulfites_declaration" in field_names

    def test_wine_sulfites_present(self, checker):
        extracted = {
            "brand_name": "CASCADE",
            "class_type": "Table Red Wine",
            "alcohol_content": "12%",
            "net_contents": "750 mL",
            "producer_name": "Cascade Winery",
            "government_warning": "GOVERNMENT WARNING: ...",
            "sulfites_declaration": "Contains Sulfites",
        }
        issues = checker.check_compliance(
            extracted, "wine", requires_sulfites=True
        )
        field_names = [i.field_name for i in issues]
        assert "sulfites_declaration" not in field_names


class TestBeerMandatoryFields:
    def test_beer_missing_abv_needs_review(self, checker):
        """Beer without ABV should be 'needs_review', not fail."""
        extracted = {
            "brand_name": "TEST BEER",
            "class_type": "Beer",
            "net_contents": "12 fl oz",
            "producer_name": "Test Brewery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(extracted, "beer")
        abv_issues = [i for i in issues if i.field_name == "alcohol_content"]
        if abv_issues:
            assert abv_issues[0].severity == "needs_review"


class TestImportedFields:
    def test_imported_requires_country(self, checker):
        extracted = {
            "brand_name": "IMPORTED BRAND",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Foreign Corp",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        field_names = [i.field_name for i in issues]
        assert "country_of_origin" in field_names

    def test_imported_importer_satisfies_producer(self, checker):
        """Fix 3: For imports, importer_name should satisfy producer_name requirement."""
        extracted = {
            "brand_name": "IMPORTED BRAND",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            # producer_name is missing/None
            "government_warning": "GOVERNMENT WARNING: ...",
            "importer_name": "Sidney Frank Importing Co.",
            "country_of_origin": "Germany",
        }
        issues = checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        field_names = [i.field_name for i in issues]
        assert "producer_name" not in field_names

    def test_imported_country_present(self, checker):
        extracted = {
            "brand_name": "IMPORTED BRAND",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Foreign Corp",
            "government_warning": "GOVERNMENT WARNING: ...",
            "country_of_origin": "Germany",
        }
        issues = checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        field_names = [i.field_name for i in issues]
        assert "country_of_origin" not in field_names
