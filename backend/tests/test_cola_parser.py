"""Tests for COLA PDF parser (TTB F 5100.31)."""

import pytest
from app.services.pdf_parser import (
    COLAPDFParser,
    _infer_beverage_type,
    _classify_panel,
    _infer_source_from_permit,
)
from tests.conftest import load_cola_pdf


class TestInferBeverageType:
    def test_spirits_default(self):
        assert _infer_beverage_type("OTHER SPECIALTIES & PROPRIETARIES") == "distilled_spirits"

    def test_spirits_liqueur(self):
        assert _infer_beverage_type("OTHER HERB & SEED CORDIALS/LIQUEURS") == "distilled_spirits"

    def test_spirits_brandy(self):
        assert _infer_beverage_type("OTHER GRAPE BRANDY (PISCO, GRAPPA) FB") == "distilled_spirits"

    def test_wine_table_red(self):
        assert _infer_beverage_type("TABLE RED WINE") == "wine"

    def test_wine_table_white(self):
        assert _infer_beverage_type("TABLE WHITE WINE") == "wine"

    def test_wine_sparkling(self):
        assert _infer_beverage_type("SPARKLING WINE/CHAMPAGNE") == "wine"

    def test_beer(self):
        assert _infer_beverage_type("MALT BEVERAGE") == "beer"


class TestClassifyPanel:
    def test_brand_front(self):
        assert _classify_panel("Brand (front) or keg collar") == "front"

    def test_back(self):
        assert _classify_panel("Back") == "back"

    def test_other(self):
        assert _classify_panel("Strip label") == "other"


class TestInferSourceFromPermit:
    def test_import_permit(self):
        assert _infer_source_from_permit("NY-I-490") == "imported"

    def test_bonded_winery(self):
        assert _infer_source_from_permit("BW-MI-159") == "domestic"

    def test_distilled_spirits_plant(self):
        assert _infer_source_from_permit("DSP-NC-15011") == "domestic"

    def test_brewer(self):
        assert _infer_source_from_permit("BR-PA-456") == "domestic"

    def test_unknown(self):
        assert _infer_source_from_permit("XX-99") is None

    def test_empty(self):
        assert _infer_source_from_permit("") is None


class TestCOLAPDFParserBarenjager:
    """Test with Barenjager PDF (newer form, imported spirits, multi-size)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = COLAPDFParser()
        self.pdf_bytes = load_cola_pdf("barenjager_imported.pdf")
        self.result = self.parser.parse(self.pdf_bytes)
        self.ad = self.result.application_data

    def test_ttb_id(self):
        assert self.ad.ttb_id == "11115001000373"

    def test_brand_name(self):
        assert self.ad.brand_name == "BARENJAGER"

    def test_fanciful_name(self):
        assert self.ad.fanciful_name == "HONEY & BOURBON"

    def test_class_type(self):
        assert self.ad.class_type == "OTHER SPECIALTIES & PROPRIETARIES"

    def test_alcohol_content(self):
        assert self.ad.alcohol_content == "35"

    def test_net_contents_multi_value(self):
        """COLA lists multiple sizes: 750 ML and 1 LITER."""
        values = self.ad.net_contents.split("\n")
        assert len(values) >= 2
        assert "750 MILLILITERS" in values[0]

    def test_source_imported(self):
        assert self.ad.source_of_product == "imported"

    def test_importer_name(self):
        assert "SIDNEY FRANK" in self.ad.importer_name

    def test_producer_not_set(self):
        assert self.ad.producer_name is None

    def test_beverage_type(self):
        assert self.ad.beverage_type == "distilled_spirits"

    def test_label_images_extracted(self):
        assert len(self.result.label_images) >= 3

    def test_image_panels(self):
        panels = [li.panel_type for li in self.result.label_images]
        assert "front" in panels
        assert "back" in panels

    def test_image_bytes_nonempty(self):
        for li in self.result.label_images:
            assert len(li.image_bytes) > 1000


class TestCOLAPDFParserCascadeWinery:
    """Test with Cascade Winery (older form, domestic wine, single label)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = COLAPDFParser()
        self.pdf_bytes = load_cola_pdf("cascade_winery_domestic.pdf")
        self.result = self.parser.parse(self.pdf_bytes)
        self.ad = self.result.application_data

    def test_ttb_id(self):
        assert self.ad.ttb_id == "03235001000006"

    def test_brand_name(self):
        assert self.ad.brand_name == "CASCADE WINERY"

    def test_class_type_wine(self):
        assert self.ad.class_type == "TABLE RED WINE"

    def test_alcohol_content(self):
        assert self.ad.alcohol_content == "11.5"

    def test_net_contents(self):
        assert "750" in self.ad.net_contents

    def test_source_domestic(self):
        assert self.ad.source_of_product == "domestic"

    def test_producer_name(self):
        assert "CASCADE WINERY" in self.ad.producer_name

    def test_importer_not_set(self):
        assert self.ad.importer_name is None

    def test_beverage_type_wine(self):
        assert self.ad.beverage_type == "wine"

    def test_single_label_image(self):
        assert len(self.result.label_images) == 1
        assert self.result.label_images[0].panel_type == "front"


class TestCOLAPDFParserMultiSize:
    """Test with Jacques Cardin (multi-size net contents)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = COLAPDFParser()
        self.pdf_bytes = load_cola_pdf("jacques_cardin_multi_size.pdf")
        self.result = self.parser.parse(self.pdf_bytes)
        self.ad = self.result.application_data

    def test_multi_net_contents(self):
        values = self.ad.net_contents.split("\n")
        assert len(values) >= 2
        assert any("375" in v for v in values)
        assert any("750" in v for v in values)

    def test_alcohol_content(self):
        assert self.ad.alcohol_content == "40"


class TestCOLAPDFParserEdgeCases:
    def test_empty_bytes(self):
        parser = COLAPDFParser()
        with pytest.raises(ValueError, match="empty"):
            parser.parse(b"")

    def test_invalid_pdf(self):
        parser = COLAPDFParser()
        with pytest.raises(ValueError, match="Failed to parse"):
            parser.parse(b"not a pdf")

    def test_stub_pdf_no_images(self):
        """Stub PDFs (single page, no content) should parse without error
        but return no label images."""
        parser = COLAPDFParser()
        # Load a known stub PDF if available
        import os
        stub_path = os.path.join(
            os.path.dirname(__file__),
            "..", "data", "applications", "11038001000727.pdf"
        )
        if os.path.exists(stub_path):
            with open(stub_path, "rb") as f:
                result = parser.parse(f.read())
            assert len(result.label_images) == 0
