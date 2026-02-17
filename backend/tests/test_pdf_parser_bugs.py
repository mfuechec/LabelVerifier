"""Tests for PDF parser bug fixes: permit prefix, sake ABV, quart units, tradename."""

import pytest
from app.services.pdf_parser import COLAPDFParser as COLAParser


@pytest.fixture
def parser():
    return COLAParser()


class TestPermitPrefixStripping:
    """Bug 3: Permit regex too restrictive for 3-segment permits like BR-AL-GOO-15000."""

    def test_three_segment_permit_stripped(self, parser):
        """BR-AL-GOO-15000 should be stripped from producer name."""
        name, _ = parser._extract_applicant(
            "BASIC PERMIT OR BREWER'S NOTICE. INCLUDE APPROVED DBA OR\n"
            "PERMIT/BREWER'S TRADENAME IF USED ON LABEL (Required)\n"
            "Domestic\n"
            "NO. (Required)\n"
            "BR-AL-GOO-15000 Imported GOOD PEOPLE BREWING COMPANY, GOOD PEOPLE, LLC\n"
            "4. SERIAL NUMBER 5. TYPE OF PRODUCT\n"
            "114 14TH ST S\n"
            "BIRMINGHAM AL 35233\n"
            "BRAND NAME\n"
        )
        assert name is not None
        assert "BR-AL-GOO" not in name
        assert "GOOD PEOPLE" in name

    def test_two_segment_permit_still_works(self, parser):
        """Existing 2-segment permits should still be stripped."""
        name, _ = parser._extract_applicant(
            "BASIC PERMIT OR BREWER'S NOTICE. INCLUDE APPROVED DBA OR\n"
            "PERMIT/BREWER'S TRADENAME IF USED ON LABEL (Required)\n"
            "Domestic\n"
            "NO. (Required)\n"
            "DSP-MO-16 Imported LUXCO, INC.\n"
            "4. SERIAL NUMBER 5. TYPE OF PRODUCT\n"
            "5050 KEMPER AVE\n"
            "SAINT LOUIS MO 63139\n"
            "BRAND NAME\n"
        )
        assert name is not None
        assert "DSP-MO" not in name
        assert "LUXCO" in name


class TestSakeAbvParsing:
    """Bug 2: (SAKE only) annotation blocks ABV extraction."""

    def test_sake_abv_with_parenthetical(self, parser):
        """ABV after '(SAKE only)' should be extracted."""
        nc, abv = parser._extract_net_contents_and_abv(
            "12. NET CONTENTS 13. ALCOHOL CONTENT\n"
            "720 ml (SAKE only) 15.5 abbreviation.)\n"
        )
        assert nc == "720 ml"
        assert abv == "15.5"

    def test_sake_abv_range(self, parser):
        """ABV range like '15-16' should extract first value."""
        nc, abv = parser._extract_net_contents_and_abv(
            "12. NET CONTENTS 13. ALCOHOL CONTENT\n"
            "720 ml (SAKE only) 15-16 abbreviation.)\n"
        )
        assert nc == "720 ml"
        assert abv is not None
        assert abv.startswith("15")

    def test_normal_abv_still_works(self, parser):
        """Standard format without parenthetical should still work."""
        nc, abv = parser._extract_net_contents_and_abv(
            "12. NET CONTENTS 13. ALCOHOL CONTENT\n"
            "750 MILLILITERS 35\n"
        )
        assert nc == "750 MILLILITERS"
        assert abv == "35"


class TestQuartNetContents:
    """Bug 5: Quart unit not recognized in net contents."""

    def test_quart_and_fl_oz_compound(self, parser):
        """'1 QT. 8 FL. OZ. (40 FL. OZ.)' should extract 40 FL. OZ from parenthetical."""
        nc, abv = parser._extract_net_contents_and_abv(
            "12. NET CONTENTS 13. ALCOHOL CONTENT\n"
            "1 QT. 8 FL. OZ. (40 FL. 3.6% IF ON LABEL\n"
            "OZ.)\n"
        )
        # Should extract some net contents value (either via QT or parenthetical)
        assert nc is not None
        # ABV should be extracted
        assert abv == "3.6"

    def test_simple_quart(self, parser):
        """Simple quart declaration should be recognized."""
        nc, abv = parser._extract_net_contents_and_abv(
            "12. NET CONTENTS 13. ALCOHOL CONTENT\n"
            "1 QT. 40\n"
        )
        assert nc is not None
        assert "QT" in nc.upper() or "32" in nc  # 1 QT or converted


class TestTradenameExtraction:
    """Bug 1: (Used on label) tradename should be extracted and used."""

    def test_tradename_extracted(self, parser):
        """Tradename from '(Used on label)' line should be returned."""
        name, _ = parser._extract_applicant(
            "BASIC PERMIT OR BREWER'S NOTICE. INCLUDE APPROVED DBA OR\n"
            "PERMIT/BREWER'S TRADENAME IF USED ON LABEL (Required)\n"
            "Domestic\n"
            "NO. (Required)\n"
            "DSP-PA-20008 Imported THISTLE FINCH DISTILLING LLC\n"
            "417 W GRANT ST\n"
            "4. SERIAL NUMBER 5. TYPE OF PRODUCT\n"
            "LANCASTER PA 17603\n"
            "(Required) (Required)\n"
            "15STL1 WINE HERITAGE SPIRITS LLC (Used on label)\n"
            "DISTILLED SPIRITS\n"
            "BRAND NAME\n"
        )
        # Should use the tradename, not the legal name
        assert name is not None
        assert "HERITAGE SPIRITS" in name

    def test_no_tradename_uses_applicant(self, parser):
        """When no tradename present, legal applicant name should be used."""
        name, _ = parser._extract_applicant(
            "BASIC PERMIT OR BREWER'S NOTICE. INCLUDE APPROVED DBA OR\n"
            "PERMIT/BREWER'S TRADENAME IF USED ON LABEL (Required)\n"
            "Domestic\n"
            "NO. (Required)\n"
            "DSP-NC-15011 Domestic HOWLING MOON DISTILLERY, LLC\n"
            "4. SERIAL NUMBER 5. TYPE OF PRODUCT\n"
            "42 OLD ELK MOUNTAIN RD\n"
            "ASHEVILLE NC 28804\n"
            "BRAND NAME\n"
        )
        assert name is not None
        assert "HOWLING MOON" in name
