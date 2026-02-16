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
