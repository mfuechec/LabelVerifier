import io
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.services.pdf_parser import PDFApplicationParser


def _generate_test_pdf(fields: list[tuple[str, str]]) -> bytes:
    """Generate a PDF matching the format from generate_packages.py."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, height - 1 * inch, "TTB Label Verification - Application Data")
    c.setLineWidth(1.5)
    c.line(1 * inch, height - 1.15 * inch, width - 1 * inch, height - 1.15 * inch)

    y = height - 1.6 * inch
    label_x = 1 * inch
    value_x = 3.2 * inch
    line_height = 0.3 * inch

    for label, value in fields:
        if label == "" and value == "":
            y -= line_height * 0.5
            continue
        c.setFont("Helvetica-Bold", 11)
        c.drawString(label_x, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(value_x, y, value)
        y -= line_height

    c.save()
    return buf.getvalue()


@pytest.fixture
def full_spirits_pdf() -> bytes:
    return _generate_test_pdf([
        ("Application ID", "APP-2026-00001"),
        ("Brand Name", "Angel's Envy"),
        ("Class/Type", "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels"),
        ("Alcohol Content", "43.3%"),
        ("Net Contents", "750 mL"),
        ("", ""),
        ("Producer Name", "Louisville Distilling Company"),
        ("Producer Address", "Louisville, Kentucky"),
        ("", ""),
        ("Country of Origin", "--"),
        ("Importer Name", "--"),
        ("Importer Address", "--"),
        ("", ""),
        ("Beverage Type", "Distilled Spirits"),
        ("Sulfites Declared", "No"),
    ])


@pytest.fixture
def wine_with_sulfites_pdf() -> bytes:
    return _generate_test_pdf([
        ("Application ID", "APP-2026-00099"),
        ("Brand Name", "Rosso Veneto"),
        ("Class/Type", "Red Wine"),
        ("Alcohol Content", "12.5%"),
        ("Net Contents", "750 mL"),
        ("", ""),
        ("Producer Name", "--"),
        ("Producer Address", "--"),
        ("", ""),
        ("Country of Origin", "Italy"),
        ("Importer Name", "Vino Imports LLC"),
        ("Importer Address", "New York, NY"),
        ("", ""),
        ("Beverage Type", "Wine"),
        ("Sulfites Declared", "Yes"),
    ])


@pytest.fixture
def beer_pdf() -> bytes:
    return _generate_test_pdf([
        ("Application ID", "--"),
        ("Brand Name", "Test IPA"),
        ("Class/Type", "India Pale Ale"),
        ("Alcohol Content", "6.5%"),
        ("Net Contents", "12 FL OZ"),
        ("", ""),
        ("Producer Name", "Craft Brewery"),
        ("Producer Address", "Portland, OR"),
        ("", ""),
        ("Country of Origin", "--"),
        ("Importer Name", "--"),
        ("Importer Address", "--"),
        ("", ""),
        ("Beverage Type", "Beer"),
        ("Sulfites Declared", "No"),
    ])


@pytest.fixture
def parser():
    return PDFApplicationParser()


class TestPDFApplicationParser:
    def test_parse_full_spirits_label(self, parser, full_spirits_pdf):
        result = parser.parse_application_pdf(full_spirits_pdf)

        assert result.application_id == "APP-2026-00001"
        assert result.brand_name == "Angel's Envy"
        assert result.class_type == "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels"
        assert result.alcohol_content == "43.3%"
        assert result.net_contents == "750 mL"
        assert result.producer_name == "Louisville Distilling Company"
        assert result.producer_address == "Louisville, Kentucky"
        assert result.country_of_origin is None
        assert result.importer_name is None
        assert result.importer_address is None
        assert result.beverage_type == "distilled_spirits"
        assert result.has_sulfites_declaration is False

    def test_parse_wine_with_sulfites(self, parser, wine_with_sulfites_pdf):
        result = parser.parse_application_pdf(wine_with_sulfites_pdf)

        assert result.brand_name == "Rosso Veneto"
        assert result.class_type == "Red Wine"
        assert result.alcohol_content == "12.5%"
        assert result.country_of_origin == "Italy"
        assert result.importer_name == "Vino Imports LLC"
        assert result.importer_address == "New York, NY"
        assert result.producer_name is None
        assert result.producer_address is None
        assert result.beverage_type == "wine"
        assert result.has_sulfites_declaration is True

    def test_parse_beer_with_null_app_id(self, parser, beer_pdf):
        result = parser.parse_application_pdf(beer_pdf)

        assert result.application_id is None
        assert result.brand_name == "Test IPA"
        assert result.beverage_type == "beer"
        assert result.has_sulfites_declaration is False

    def test_parse_real_pdf_from_test_data(self, parser):
        """Test against an actual generated PDF from test data packages."""
        import os
        pdf_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "test data", "packages", "pass", "angels-envy", "application.pdf"
        )
        if not os.path.exists(pdf_path):
            pytest.skip("Test data packages not generated yet")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        result = parser.parse_application_pdf(pdf_bytes)
        assert result.brand_name == "Angel's Envy"
        assert result.beverage_type == "distilled_spirits"
        assert result.alcohol_content == "43.3%"

    def test_parse_invalid_pdf_raises(self, parser):
        with pytest.raises(ValueError, match="Failed to parse PDF"):
            parser.parse_application_pdf(b"not a pdf")

    def test_parse_empty_pdf_raises(self, parser):
        with pytest.raises(ValueError):
            parser.parse_application_pdf(b"")
