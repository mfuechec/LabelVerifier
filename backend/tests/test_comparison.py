"""Tests for ComparisonService end-to-end field comparison."""

import pytest
from app.models.schemas import ApplicationData
from app.services.comparison import ComparisonService


@pytest.fixture
def service():
    return ComparisonService()


class TestCompareFieldsPassCase:
    """All fields match correctly -- expect all 'match' status."""

    def test_all_fields_match(self, service, sample_application_data):
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": "Other Specialties",
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "producer_name": "HOWLING MOON, THE COPPER STILL LLC",
            "producer_address": "123 MAIN ST, ASHEVILLE NC 28801",
            "government_warning": (
                "GOVERNMENT WARNING: (1) According to the Surgeon General, "
                "women should not drink alcoholic beverages during pregnancy "
                "because of the risk of birth defects. (2) Consumption of "
                "alcoholic beverages impairs your ability to drive a car or "
                "operate machinery, and may cause health problems."
            ),
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        statuses = {r.field_name: r.status for r in results}
        assert statuses["brand_name"] == "match"
        assert statuses["alcohol_content"] == "match"
        assert statuses["net_contents"] == "match"
        assert statuses["government_warning"] == "match"


class TestCompareFieldsBrandMismatch:
    """Tampered brand name -- expect content_mismatch."""

    def test_wrong_brand(self, service, sample_application_data):
        extracted = {
            "brand_name": "COMPLETELY DIFFERENT BRAND",
            "class_type": "Other Specialties",
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        assert brand.status == "content_mismatch"


class TestCompareFieldsMissingWarning:
    """Government warning not found on label."""

    def test_missing_warning(self, service, sample_application_data):
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": "Other Specialties",
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "field_missing"


class TestCompareFieldsMultiValueNetContents:
    """COLA declares multiple sizes; label shows one."""

    def test_match_any_declared_size(self, service):
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="375 MILLILITERS\n750 MILLILITERS\n1 LITER",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "alcohol_content": "40%",
            "net_contents": "1 L",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        nc = next(r for r in results if r.field_name == "net_contents")
        assert nc.status == "match"


class TestCompareFieldsAbvMismatch:
    """ABV on label doesn't match declared value."""

    def test_wrong_abv(self, service, sample_application_data):
        extracted = {
            "brand_name": "HOWLING MOON",
            "alcohol_content": "80% ABV",  # declared is 50
            "net_contents": "750 mL",
            "government_warning": "N/A",
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        abv = next(r for r in results if r.field_name == "alcohol_content")
        assert abv.status == "content_mismatch"


class TestCompareFieldsExtractionConfidence:
    """Low extraction confidence should flag as uncertain."""

    def test_low_confidence_overrides_match(self, service, sample_application_data):
        extracted = {
            "brand_name": "HOWLING MOON",
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
        }
        confidences = {"brand_name": "low"}
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits",
            extraction_confidences=confidences,
        )
        brand = next(r for r in results if r.field_name == "brand_name")
        assert brand.status == "extraction_uncertain"
        assert brand.extraction_confidence == "low"


class TestCompareFieldsImportedApplication:
    """Imported application -- importer fields should be compared."""

    def test_importer_match(self, service, sample_imported_application):
        extracted = {
            "brand_name": "BARENJAGER",
            "class_type": "OTHER SPECIALTIES & PROPRIETARIES",
            "alcohol_content": "35%",
            "net_contents": "750 mL",
            "importer_name": "Sidney Frank Importing Co., Inc.",
            "government_warning": "N/A",
        }
        results = service.compare_fields(
            extracted, sample_imported_application, "distilled_spirits"
        )
        imp = next(r for r in results if r.field_name == "importer_name")
        assert imp.status == "match"


class TestCompareFieldsSpecialtyClass:
    """Administrative COLA codes should use specialty class matching."""

    def test_specialty_with_data_matches(self, service, sample_application_data):
        """When _specialty_class_data is present with both fields, class_type should match."""
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": None,  # won't match verbatim -- but specialty data present
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Midnight Moonshine",
                "composition_statement": "Corn whiskey with natural flavors",
            },
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.status == "match"
        assert ct.confidence == 100.0
        assert ct.match_strategy == "specialty_class"

    def test_specialty_without_data_falls_back(self, service, sample_application_data):
        """Without _specialty_class_data, admin codes still go through normal class_type_match."""
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": None,
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        ct = next(r for r in results if r.field_name == "class_type")
        # Without specialty data and null extracted, this should be field_missing
        assert ct.status == "field_missing"

    def test_specialty_partial_data(self, service, sample_application_data):
        """Only fanciful name present -- should match at lower confidence."""
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": None,
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Midnight Moonshine",
                "composition_statement": None,
            },
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.status == "match"
        assert ct.confidence == 85.0

    def test_specialty_display_values(self, service, sample_application_data):
        """Declared should show COLA text, extracted should show fanciful + composition."""
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": None,
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Midnight Moonshine",
                "composition_statement": "Corn whiskey with natural flavors",
            },
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.declared_value == "OTHER SPECIALTIES & PROPRIETARIES"
        assert "Midnight Moonshine" in ct.extracted_value

    def test_non_admin_class_type_ignores_specialty_data(self, service):
        """Regular class types should NOT use specialty matching even if _specialty_class_data exists."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 MILLILITERS",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Something",
                "composition_statement": "Something else",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        # Should use normal class_type matching, not specialty
        assert ct.match_strategy == "class_type"

    # Fix #1: Re-extraction should fire even when LLM extracted something for class_type
    def test_specialty_with_data_overrides_extracted_class(self, service, sample_application_data):
        """When _specialty_class_data is present, it takes priority even if class_type was extracted."""
        extracted = {
            "brand_name": "HOWLING MOON",
            "class_type": "Liqueur",  # LLM found something -- should still use specialty path
            "alcohol_content": "50% ABV",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Midnight Moonshine",
                "composition_statement": "Corn whiskey with natural flavors",
            },
        }
        results = service.compare_fields(
            extracted, sample_application_data, "distilled_spirits"
        )
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.match_strategy == "specialty_class"
        assert ct.status == "match"

    # Fix #3: COLA fanciful_name passed into specialty comparison
    def test_specialty_verifies_declared_fanciful_name(self, service):
        """Specialty match should verify extracted fanciful name against COLA's fanciful_name."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 MILLILITERS",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "BARENJAGER",
            "class_type": "Honey Liqueur",
            "alcohol_content": "35%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Honey & Bourbon",
                "composition_statement": "Honey flavored liqueur with bourbon",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.status == "match"
        assert ct.confidence == 100.0

class TestImporterNameMatch:
    """Importer name matching should handle common abbreviation differences."""

    def test_ampersand_vs_and_matches(self, service):
        """'Fotis and Son Imports' should match 'FOTIS & SON IMPORTS, INC.'."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            importer_name="FOTIS & SON IMPORTS, INC.",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "importer_name": "Fotis and Son Imports",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        imp = next(r for r in results if r.field_name == "importer_name")
        assert imp.status == "match"

    def test_abbreviated_company_name_matches(self, service):
        """'W. & S.' should match 'NICHE W.& S., NICHE IMPORT COMPANY' (containment)."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            importer_name="NICHE W.& S., NICHE IMPORT COMPANY",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "importer_name": "Niche W & S",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        imp = next(r for r in results if r.field_name == "importer_name")
        assert imp.status == "match"

    def test_wrong_importer_does_not_match(self, service):
        """Completely different importer should fail."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            importer_name="FOTIS & SON IMPORTS, INC.",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "importer_name": "Completely Different Company",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        imp = next(r for r in results if r.field_name == "importer_name")
        assert imp.status == "content_mismatch"


class TestAddressPartialMatch:
    """Labels often show only city/state while applications have full street addresses."""

    def test_city_state_matches_full_address(self, service):
        """'Asheville, North Carolina' should match '42 OLD ELK MOUNTAIN RD, ASHEVILLE NC 28801'."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            producer_address="42 OLD ELK MOUNTAIN RD, ASHEVILLE NC 28801",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "TEST PRODUCER",
            "producer_address": "Asheville, North Carolina",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        addr = next(r for r in results if r.field_name == "producer_address")
        assert addr.status == "match"

    def test_city_state_abbrev_matches_full_address(self, service):
        """'NEW ROCHELLE, N.Y.' should match '20 CEDAR ST, NEW ROCHELLE NY 10801'."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            importer_name="TEST IMPORTER",
            importer_address="20 CEDAR ST, NEW ROCHELLE NY 10801",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "importer_name": "TEST IMPORTER",
            "importer_address": "NEW ROCHELLE, N.Y.",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        addr = next(r for r in results if r.field_name == "importer_address")
        assert addr.status == "match"

    def test_wrong_city_does_not_match(self, service):
        """'Boston, MA' should NOT match '42 OLD ELK MOUNTAIN RD, ASHEVILLE NC 28801'."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            producer_name="TEST PRODUCER",
            producer_address="42 OLD ELK MOUNTAIN RD, ASHEVILLE NC 28801",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "TEST PRODUCER",
            "producer_address": "Boston, MA",
            "government_warning": "N/A",
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        addr = next(r for r in results if r.field_name == "producer_address")
        assert addr.status == "content_mismatch"


class TestSpecialtyClassAdminCodes:
    """Administrative COLA codes should use specialty class matching."""

    def test_other_cordials_uses_specialty_matching(self, service):
        """'OTHER HERB & SEED CORDIALS/LIQUEURS' should use specialty_class path, not fuzzy."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY LIQUEUR",
            class_type="OTHER HERB & SEED CORDIALS/LIQUEURS",
            alcohol_content="35",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "BARENJAGER",
            "class_type": "Honey Liqueur",
            "alcohol_content": "35%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Honey Liqueur",
                "composition_statement": "Honey flavored liqueur",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.match_strategy == "specialty_class"
        assert ct.status == "match"

    def test_other_grape_brandy_uses_specialty_matching(self, service):
        """'OTHER GRAPE BRANDY (PISCO, GRAPPA) FB' should use specialty_class path."""
        app_data = ApplicationData(
            brand_name="VIEJO TONEL",
            fanciful_name="PISCO",
            class_type="OTHER GRAPE BRANDY (PISCO, GRAPPA) FB",
            alcohol_content="42",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "VIEJO TONEL",
            "class_type": "Pisco",
            "alcohol_content": "42%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Pisco",
                "composition_statement": "Grape brandy",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.match_strategy == "specialty_class"
        assert ct.status == "match"

    def test_warning_missing_space_after_number_matches(self, service):
        """Government warning with '(1)According' (no space) should still match."""
        app_data = ApplicationData(
            brand_name="TEST",
            class_type="VODKA",
            alcohol_content="40",
            net_contents="750 mL",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "TEST",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "government_warning": (
                "GOVERNMENT WARNING: (1)According to the Surgeon General, "
                "women should not drink alcoholic beverages during pregnancy "
                "because of the risk of birth defects. (2)Consumption of "
                "alcoholic beverages impairs your ability to drive a car or "
                "operate machinery, and may cause health problems."
            ),
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        warning = next(r for r in results if r.field_name == "government_warning")
        assert warning.status == "match"

    def test_specialty_fanciful_name_mismatch_flags(self, service):
        """When extracted fanciful name doesn't match COLA's, flag as content_mismatch."""
        app_data = ApplicationData(
            brand_name="BARENJAGER",
            fanciful_name="HONEY & BOURBON",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="35",
            net_contents="750 MILLILITERS",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "BARENJAGER",
            "class_type": None,
            "alcohol_content": "35%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Totally Wrong Name",
                "composition_statement": "Honey flavored liqueur",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.status == "content_mismatch"

    def test_specialty_fanciful_in_composition_matches(self, service):
        """When LLM puts the fanciful name into composition_statement, still match.

        Real case: Howling Moon-1 — COLA declares fanciful 'RAYMOND FAIRCHILDS MOUNTAIN',
        LLM extracts fanciful='Howling Moon' (the brand) and
        composition="Raymond Fairchild's Mountain Moonshine" (contains the fanciful).
        """
        app_data = ApplicationData(
            brand_name="HOWLING MOON",
            fanciful_name="RAYMOND FAIRCHILDS MOUNTAIN",
            class_type="OTHER SPECIALTIES & PROPRIETARIES",
            alcohol_content="50",
            net_contents="750 MILLILITERS",
            beverage_type="distilled_spirits",
        )
        extracted = {
            "brand_name": "Howling Moon",
            "class_type": None,
            "alcohol_content": "50%",
            "net_contents": "750 mL",
            "government_warning": "N/A",
            "_specialty_class_data": {
                "fanciful_name": "Howling Moon",
                "composition_statement": "Raymond Fairchild's Mountain Moonshine",
            },
        }
        results = service.compare_fields(extracted, app_data, "distilled_spirits")
        ct = next(r for r in results if r.field_name == "class_type")
        assert ct.status == "match"
