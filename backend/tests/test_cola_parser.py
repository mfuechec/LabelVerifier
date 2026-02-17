"""Tests for COLA PDF parser (TTB F 5100.31)."""

import fitz  # PyMuPDF
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
        # Signature images filtered; real labels (including thin strips) remain
        assert len(self.result.label_images) >= 3

    def test_image_panels(self):
        panels = [li.panel_type for li in self.result.label_images]
        assert "front" in panels

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

    def test_real_pdf_with_small_labels(self):
        """PDFs with small but real label images should still extract them.

        11038001000727.pdf has banner (772x194, filtered) + two small labels.
        """
        parser = COLAPDFParser()
        import os
        pdf_path = os.path.join(
            os.path.dirname(__file__),
            "..", "data", "applications", "11038001000727.pdf"
        )
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                result = parser.parse(f.read())
            # Banner filtered, real labels kept
            assert len(result.label_images) >= 2


def _make_pdf_no_xobject_images(num_pages: int = 2) -> bytes:
    """Create a PDF with text-only pages (no XObject images).

    Page 1 = form text, pages 2+ = text only (no embedded images).
    """
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1} - text content only")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_pdf_with_image_on_page(page_with_image: int, total_pages: int = 3) -> bytes:
    """Create a PDF where one page has an embedded XObject image and others don't.

    page_with_image is 0-indexed.
    """
    import os
    import struct
    import zlib

    doc = fitz.open()
    for i in range(total_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1}")
        if i == page_with_image:
            # Insert a large enough image with random pixels so it exceeds
            # _MIN_IMAGE_BYTES (5000) after compression.
            width, height = 300, 300
            raw_data = b""
            for _ in range(height):
                raw_data += b"\x00" + os.urandom(width * 3)  # random RGB
            compressed = zlib.compress(raw_data)

            # Minimal PNG
            def _chunk(ctype, data):
                c = ctype + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

            png = b"\x89PNG\r\n\x1a\n"
            png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            png += _chunk(b"IDAT", compressed)
            png += _chunk(b"IEND", b"")

            rect = fitz.Rect(72, 150, 400, 500)
            page.insert_image(rect, stream=png)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_pdf_with_annotation(pages_with_annotation: list[int], total_pages: int = 3) -> bytes:
    """Create a PDF where specific pages have 'Image Type:' annotations.

    pages_with_annotation is 0-indexed page numbers that get annotation text.
    Annotated pages also get a large coloured rectangle so the pixmap fallback
    produces a non-white image (real label pages contain visual content).
    Pages without annotations and without XObject images simulate form pages.
    """
    doc = fitz.open()
    for i in range(total_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1}")
        if i in pages_with_annotation:
            page.insert_text((72, 200), "Image Type:\nBrand (front) or keg collar")
            # Draw a large coloured rectangle to simulate visual label content
            rect = fitz.Rect(50, 250, 550, 700)
            page.draw_rect(rect, color=(0, 0.5, 0.8), fill=(0.2, 0.6, 0.9), width=3)
            page.insert_text((200, 450), "LABEL CONTENT", fontsize=36)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestImageTypeAnnotations:
    """Tests for per-page annotation extraction."""

    def test_returns_dict_keyed_by_page_number(self):
        """Annotations should be returned as dict[int, list[str]]."""
        parser = COLAPDFParser()
        # Page 0 = no annotation, page 1 = has annotation
        pdf_bytes = _make_pdf_with_annotation([1], total_pages=2)
        result = parser._extract_image_type_annotations(pdf_bytes)
        assert isinstance(result, dict)
        assert 1 in result
        assert result[1] == ["Brand (front) or keg collar"]

    def test_pages_without_annotation_absent_from_dict(self):
        """Pages with no 'Image Type:' text should not appear in the dict."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_annotation([1], total_pages=3)
        result = parser._extract_image_type_annotations(pdf_bytes)
        assert 0 not in result
        assert 2 not in result


def _make_png(width: int, height: int, white: bool = False) -> bytes:
    """Create a minimal PNG image.

    If white=True, creates a mostly-white image (simulating a signature).
    Otherwise creates a random-colour image (simulating a label).
    """
    import os
    import struct
    import zlib

    raw_data = b""
    for _ in range(height):
        if white:
            # ~95% white pixels with a thin grey squiggle
            row = b"\xff\xff\xff" * width
            raw_data += b"\x00" + row
        else:
            raw_data += b"\x00" + os.urandom(width * 3)
    compressed = zlib.compress(raw_data)

    def _chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    return png


def _make_pdf_with_banner_and_label(
    banner_size: tuple[int, int] = (772, 195),
    label_size: tuple[int, int] = (400, 400),
    signature_style: bool = True,
    total_pages: int = 2,
) -> bytes:
    """Create a PDF where page 2 has a signature image and a label image.

    The banner simulates a TTB officer signature (~772x195px, mostly white).
    When signature_style=False the banner is colorful (simulating a label strip).
    """
    doc = fitz.open()
    for i in range(total_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1}")
        if i == 1:
            page.insert_text((72, 200), "Image Type:\nBrand (front) or keg collar")
            # Signature image (thin wide strip)
            png = _make_png(*banner_size, white=signature_style)
            page.insert_image(
                fitz.Rect(10, 210, 10 + banner_size[0] * 0.5, 210 + banner_size[1] * 0.5),
                stream=png,
            )
            # Real label image
            png = _make_png(*label_size, white=False)
            page.insert_image(
                fitz.Rect(72, 300, 72 + label_size[0] * 0.5, 300 + label_size[1] * 0.5),
                stream=png,
            )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_pdf_with_certificate_page() -> bytes:
    """Create a PDF where page 2 has a label and page 3 is a certificate page.

    Page 3 has 'Image Type:' annotation AND 'AUTHORIZED SIGNATURE' boilerplate,
    simulating a TTB certificate page that should NOT trigger pixmap fallback.
    """
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Page {i + 1}")
        if i == 1:
            page.insert_text((72, 200), "Image Type:\nBrand (front) or keg collar")
            png = _make_png(400, 400, white=False)
            page.insert_image(fitz.Rect(72, 250, 350, 550), stream=png)
        elif i == 2:
            # Certificate page with annotation AND boilerplate
            page.insert_text((72, 200), "Image Type:\nBack")
            page.insert_text((72, 400), "23. AUTHORIZED SIGNATURE, ALCOHOL AND TOBACCO TAX AND TRADE BUREAU")
            page.insert_text((72, 700), "TTB F 5100.31 PREVIOUS EDITIONS ARE OBSOLETE")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestSignatureImageFiltering:
    """Tests for filtering TTB officer signature images from label extraction."""

    def test_signature_image_filtered_label_kept(self):
        """A 772x195 white signature image should be filtered; the label kept."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_banner_and_label(
            banner_size=(772, 195), label_size=(400, 400),
            signature_style=True,
        )
        images = parser._extract_label_images(pdf_bytes)
        # Only the label should remain, not the signature
        assert len(images) == 1
        assert images[0].panel_type == "front"

    def test_colorful_thin_strip_kept(self):
        """A thin wide label strip with color content should NOT be filtered."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_banner_and_label(
            banner_size=(725, 175), label_size=(400, 400),
            signature_style=False,  # colorful → real label strip
        )
        images = parser._extract_label_images(pdf_bytes)
        # Both images should be kept (strip has color, not a signature)
        assert len(images) == 2

    def test_colorful_tall_wide_image_not_filtered(self):
        """A colorful image with height >= 200 is not caught by the aspect ratio gate."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_banner_and_label(
            banner_size=(800, 250), label_size=(400, 400),
            signature_style=False,  # colorful so it exceeds _MIN_IMAGE_BYTES
        )
        images = parser._extract_label_images(pdf_bytes)
        # Both kept: the aspect ratio gate (short < 200 and ratio > 3) doesn't fire
        assert len(images) == 2


class TestCertificatePageFiltering:
    """Tests for filtering certificate/signature pages from pixmap fallback."""

    def test_certificate_page_excluded_from_annotations(self):
        """Pages with AUTHORIZED SIGNATURE should not get annotations."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_certificate_page()
        annotations = parser._extract_image_type_annotations(pdf_bytes)
        # Page 1 (label) should have annotation, page 2 (certificate) should not
        assert 1 in annotations
        assert 2 not in annotations

    def test_certificate_page_no_pixmap_fallback(self):
        """Certificate pages should not produce pixmap images."""
        parser = COLAPDFParser()
        pdf_bytes = _make_pdf_with_certificate_page()
        images = parser._extract_label_images(pdf_bytes)
        # Only the label page image, not the certificate page
        assert len(images) == 1
        assert images[0].panel_type == "front"


class TestPixmapFallback:
    """Tests for pixmap fallback when get_images() finds no XObject images."""

    def test_form_page_skipped_no_images_no_annotations(self):
        """Page with no XObject images AND no annotations should be skipped."""
        parser = COLAPDFParser()
        # 2 pages, neither has annotations -- page 2 (index 1) has no images
        pdf_bytes = _make_pdf_no_xobject_images(num_pages=2)
        images = parser._extract_label_images(pdf_bytes)
        assert len(images) == 0

    def test_fallback_when_annotation_present(self):
        """Page with no XObject images BUT with annotation should get pixmap."""
        parser = COLAPDFParser()
        # page 0 = form, page 1 = has annotation (label page)
        pdf_bytes = _make_pdf_with_annotation([1], total_pages=2)
        images = parser._extract_label_images(pdf_bytes)
        assert len(images) == 1
        assert images[0].image_bytes[:4] == b"\x89PNG"
        assert images[0].panel_type == "front"

    def test_xobject_path_still_used_when_images_present(self):
        """Barenjager PDF has XObject images -- signatures filtered, labels kept."""
        parser = COLAPDFParser()
        pdf_bytes = load_cola_pdf("barenjager_imported.pdf")
        images = parser._extract_label_images(pdf_bytes)
        assert len(images) >= 3

    def test_mixed_pages_xobject_and_form_skipped(self):
        """PDF with XObject image on page 2 and text-only form page 3.

        Form page (no annotations, no images) should be skipped.
        """
        parser = COLAPDFParser()
        # page 0 = form (skipped by range), page 1 = has image, page 2 = text only no annotation
        pdf_bytes = _make_pdf_with_image_on_page(page_with_image=1, total_pages=3)
        images = parser._extract_label_images(pdf_bytes)
        assert len(images) == 1  # only the XObject image page
