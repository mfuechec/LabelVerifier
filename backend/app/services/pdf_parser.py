"""COLA PDF Parser for TTB F 5100.31 applications.

Parses both form versions:
- OMB 1513-0020 (newer): has SOURCE OF PRODUCT field
- OMB 1512-0092 (older): no SOURCE OF PRODUCT, different field numbering

Extracts application data from page 1 (text via pdfplumber) and
label images from pages 2+ (embedded images via PyMuPDF/fitz).
"""

import io
import re
from dataclasses import dataclass

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

from app.models.schemas import ApplicationData


@dataclass
class LabelImage:
    image_bytes: bytes
    panel_type: str  # "front", "back", "other"
    image_type_raw: str  # e.g. "Brand (front) or keg collar"


@dataclass
class COLAParseResult:
    application_data: ApplicationData
    label_images: list[LabelImage]


# Minimum image size in bytes to filter out logos/signatures/icons
_MIN_IMAGE_BYTES = 5000
# Minimum image dimensions (pixels) to filter out tiny images
_MIN_IMAGE_DIM = 80


# Beverage type inference from CLASS/TYPE DESCRIPTION
_WINE_KEYWORDS = [
    "wine", "champagne", "sparkling", "table red", "table white",
    "dessert", "vermouth", "sherry", "port", "madeira", "marsala",
    "sake", "mead",
]
_BEER_KEYWORDS = [
    "beer", "ale", "lager", "stout", "malt beverage", "malt liquor",
    "porter", "pilsner",
]


def _infer_beverage_type(class_type: str) -> str:
    """Infer beverage type from CLASS/TYPE DESCRIPTION."""
    lower = class_type.lower()
    for kw in _WINE_KEYWORDS:
        if kw in lower:
            return "wine"
    for kw in _BEER_KEYWORDS:
        if kw in lower:
            return "beer"
    return "distilled_spirits"


def _is_signature_image(image_bytes: bytes, white_threshold: float = 0.80) -> bool:
    """Detect TTB officer signature images (handwriting on white background).

    Signature images are overwhelmingly white (>80%) and nearly fully
    grayscale (>95%).  Real label strips -- even thin ones like neck bands
    -- contain colour and much less white space.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return False

    # get_flattened_data() replaces getdata() in Pillow 14+
    pixels = img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()
    total = len(pixels)
    if total == 0:
        return False

    white_count = 0
    gray_count = 0
    for r, g, b in pixels:
        if r > 240 and g > 240 and b > 240:
            white_count += 1
        if abs(r - g) < 15 and abs(g - b) < 15:
            gray_count += 1

    white_pct = white_count / total
    gray_pct = gray_count / total

    return white_pct >= white_threshold and gray_pct >= 0.95


def _classify_panel(image_type_text: str) -> str:
    """Map image type annotation to panel type."""
    lower = image_type_text.lower()
    if "front" in lower or "brand" in lower or "collar" in lower:
        return "front"
    if "back" in lower:
        return "back"
    return "other"


def _infer_source_from_permit(permit: str) -> str | None:
    """Infer domestic/imported from permit prefix on older forms.

    Import permits contain '-I-' (e.g., NY-I-490).
    Bonded winery: BW-*, Distilled spirits plant: DSP-*, Brewer: BR-*
    """
    if not permit:
        return None
    upper = permit.upper()
    if "-I-" in upper:
        return "imported"
    if any(upper.startswith(p) for p in ("BW-", "DSP-", "BR-")):
        return "domestic"
    return None


class COLAPDFParser:
    """Parse TTB F 5100.31 COLA PDFs into structured data + label images."""

    def parse(self, pdf_bytes: bytes) -> COLAParseResult:
        """Parse a COLA PDF into application data + label images."""
        if not pdf_bytes:
            raise ValueError("Failed to parse PDF: empty input")

        app_data = self._extract_form_data(pdf_bytes)
        label_images = self._extract_label_images(pdf_bytes)

        return COLAParseResult(
            application_data=app_data,
            label_images=label_images,
        )

    def _detect_form_version(self, text: str) -> str:
        """Detect OMB form version from page 1 text.

        Returns '1513-0020' or '1512-0092'.
        """
        if "SOURCE OF" in text and "PRODUCT" in text:
            return "1513-0020"
        return "1512-0092"

    def _extract_form_data(self, pdf_bytes: bytes) -> ApplicationData:
        """Extract application fields from page 1 text via pdfplumber."""
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {e}") from e

        if not pdf.pages:
            pdf.close()
            raise ValueError("Failed to parse PDF: no pages found")

        text = pdf.pages[0].extract_text() or ""

        # Also extract text from subsequent pages for CLASS/TYPE
        all_text = text
        for page in pdf.pages[1:]:
            all_text += "\n" + (page.extract_text() or "")
        pdf.close()

        if not text.strip():
            raise ValueError("Failed to parse PDF: no text content found")

        version = self._detect_form_version(text)

        # TTB ID
        ttb_id = self._extract_ttb_id(text)

        # CLASS/TYPE DESCRIPTION (from certificate section, usually page 2+)
        class_type = self._extract_class_type(all_text)

        # Brand name
        brand_name = self._extract_brand_name(text)

        # Fanciful name
        fanciful_name = self._extract_fanciful_name(text)

        # Applicant name and address
        applicant_name, applicant_address = self._extract_applicant(text)

        # Permit number (for source inference on older forms)
        permit = self._extract_permit(text)

        # Source of product
        source = self._extract_source(text, version, permit)

        # Net contents and alcohol content (side-by-side in form)
        net_contents, alcohol_content = self._extract_net_contents_and_abv(text)

        # Beverage type from class/type description
        beverage_type = _infer_beverage_type(class_type) if class_type else "distilled_spirits"

        # Route applicant to producer or importer based on source
        producer_name = None
        producer_address = None
        importer_name = None
        importer_address = None

        if source == "imported":
            importer_name = applicant_name
            importer_address = applicant_address
        else:
            producer_name = applicant_name
            producer_address = applicant_address

        return ApplicationData(
            ttb_id=ttb_id,
            brand_name=brand_name or "",
            fanciful_name=fanciful_name,
            class_type=class_type or "",
            alcohol_content=alcohol_content or "",
            net_contents=net_contents or "",
            producer_name=producer_name,
            producer_address=producer_address,
            importer_name=importer_name,
            importer_address=importer_address,
            beverage_type=beverage_type,
            source_of_product=source,
        )

    def _extract_ttb_id(self, text: str) -> str | None:
        """Extract TTB ID from top of form."""
        match = re.search(r"TTB ID\s+APPLICATION.*?\n(\d+)", text)
        if match:
            return match.group(1)
        return None

    def _extract_class_type(self, text: str) -> str | None:
        """Extract CLASS/TYPE DESCRIPTION from certificate section."""
        match = re.search(r"CLASS/TYPE DESCRIPTION\n(.+)", text)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\s*https?://.*$", "", value)
            return value if value else None
        return None

    def _extract_brand_name(self, text: str) -> str | None:
        """Extract brand name from form."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "BRAND NAME" in line and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r"^(\d+\.\s|FANCIFUL|EMAIL)", next_line):
                    return next_line
        return None

    def _extract_fanciful_name(self, text: str) -> str | None:
        """Extract fanciful name from form."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "FANCIFUL NAME" in line:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not re.match(
                        r"^(\d+\.\s|EMAIL|FORMULA|MAILING)", next_line
                    ):
                        return next_line
        return None

    def _extract_applicant(self, text: str) -> tuple[str | None, str | None]:
        """Extract applicant name and address.

        The applicant block (field 7/8) is in the right column of the form.
        In pdfplumber output, it may appear:
        - On its own line (permit + name), or
        - Merged with left-column text (SERIAL NUMBER line contains applicant name)
        """
        lines = text.split("\n")

        # Strategy: collect candidate lines from the applicant region
        applicant_lines = []
        tradename = None
        in_applicant = False
        past_serial = False

        for line in lines:
            if line.strip() == "NO. (Required)" or (
                "NO. (Required)" in line and "BASIC PERMIT" in line
            ):
                in_applicant = True
                continue
            if not in_applicant:
                continue

            cleaned = line.strip()

            # Skip form label lines
            if not cleaned or re.match(
                r"^(Domestic$|Imported$|BASIC\s|TRADENAME|PLANT\s)", cleaned
            ):
                continue

            # Check for SERIAL NUMBER / TYPE OF PRODUCT line which may contain
            # applicant name in the right portion
            if "SERIAL NUMBER" in line:
                past_serial = True
                # Extract text after form labels on this line
                # Pattern: "3. SERIAL NUMBER 4. TYPE OF PRODUCT APPLICANT NAME"
                after = re.sub(
                    r"^.*?(?:TYPE OF PRODUCT|PRODUCT\s*\(Required\))\s*",
                    "",
                    cleaned,
                )
                if after and after != cleaned:
                    applicant_lines.append(after)
                continue

            if past_serial:
                # Check for tradename line: "140161 WINE SAILOR JERRY RUM (Used on label)"
                if "(Used on label)" in cleaned:
                    # Strip serial/product-type prefix and "(Used on label)" suffix
                    # Serial formats: "140161", "15STL1", "1606BA", etc.
                    tn = re.sub(r"\s*\(Used on label\)\s*$", "", cleaned)
                    tn = re.sub(
                        r"^[\dA-Z]+\s+(?:WINE|DISTILLED SPIRITS|MALT BEVERAGE)\s+",
                        "", tn,
                    ).strip()
                    if tn:
                        tradename = tn
                    continue
                # Lines after SERIAL NUMBER may have address in right column
                # "(Required) (Required) 134 N 3300 E" -> extract address part
                after = re.sub(r"^\(Required\)\s*\(Required\)\s*", "", cleaned)
                if after != cleaned and after:
                    applicant_lines.append(after)
                    continue
                # Stop at BRAND NAME or product type lines
                if "BRAND NAME" in cleaned or "MAILING ADDRESS" in cleaned:
                    break
                # Skip product type options and serial numbers
                if re.match(r"^(WINE$|DISTILLED SPIRITS$|MALT BEVERAGE$|\d+[A-Z])", cleaned):
                    continue
                # City/state/zip line (e.g., "RIGBY ID 83442" or "GRAND RAPIDS MI 49546")
                if re.match(r"^[A-Z]", cleaned) and not re.match(r"^\d+\.\s", cleaned):
                    applicant_lines.append(cleaned)
                    continue
            else:
                # Before SERIAL NUMBER: permit line or applicant name
                if "BRAND NAME" in cleaned:
                    break
                applicant_lines.append(cleaned)

        if not applicant_lines:
            return (None, None)

        # First line may contain permit number + "Imported"/"Domestic" + applicant name
        # Permit formats: BW-NJ-68, NY-I-490, DSP-NC-15011, DSP-ID-2, BR-AL-GOO-15000
        first = applicant_lines[0]
        name_part = re.sub(
            r"^[A-Z]{1,4}(?:-[A-Z]{1,3}){1,3}-\d+\s*(?:Imported|Domestic)?\s*",
            "",
            first,
        ).strip()

        if name_part:
            name = name_part
            address_lines = applicant_lines[1:]
        elif len(applicant_lines) > 1:
            name = applicant_lines[1]
            address_lines = applicant_lines[2:]
        else:
            return (None, None)

        name = re.sub(r"\s*\(Used on label\)\s*$", "", name).strip()

        # Prefer tradename (DBA) over legal applicant name — it's what appears on the label
        if tradename:
            name = tradename

        addr_parts = []
        for line in address_lines:
            if re.match(r"^\d+\.\s", line) or "MAILING ADDRESS" in line:
                break
            # Strip "(Used on label)" COLA form annotations from address lines
            cleaned_line = re.sub(r"\s*\(Used on label\)\s*", "", line).strip()
            if cleaned_line:
                addr_parts.append(cleaned_line)

        address = ", ".join(addr_parts) if addr_parts else None

        return (name if name else None, address)

    def _extract_permit(self, text: str) -> str | None:
        """Extract permit/registry number.

        Formats: BW-MI-159, NY-I-490, DSP-CA-123, BR-PA-456
        """
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "NO. (Required)" in line:
                for j in range(max(0, i - 1), min(len(lines), i + 4)):
                    match = re.search(
                        r"\b([A-Z]{1,4}-[A-Z]{1,2}-\d+)\b", lines[j]
                    )
                    if match:
                        return match.group(1)
        return None

    def _extract_source(
        self, text: str, version: str, permit: str | None
    ) -> str | None:
        """Extract source of product (domestic/imported).

        Both "Domestic" and "Imported" text labels appear in pdfplumber output
        regardless of which checkbox is checked. The permit prefix is the
        reliable indicator.
        """
        if permit:
            inferred = _infer_source_from_permit(permit)
            if inferred:
                return inferred
        return None

    def _extract_net_contents_and_abv(self, text: str) -> tuple[str | None, str | None]:
        """Extract net contents and alcohol content from the combined field area.

        In COLA PDFs, the NET CONTENTS and ALCOHOL CONTENT columns are side-by-side.
        pdfplumber renders them on the same line, e.g.:
            "750 MILLILITERS 35"
            "375 MILLILITERS 40 IF ON LABEL ..."
        The ABV is the number after the first net contents value.
        Multiple net contents values may appear on subsequent lines.
        """
        _NC_PATTERN = re.compile(
            r"(\d+\.?\d*\s*(?:MILLILITERS?|LITERS?|ML|L|FL\.?\s*OZ|QT\.?|QUARTS?|GAL\.?|GALLONS?|PT\.?|PINTS?))",
            re.IGNORECASE,
        )

        lines = text.split("\n")
        nc_values = []
        abv = None

        in_contents = False
        for line in lines:
            if "NET CONTENTS" in line:
                in_contents = True
                continue
            if not in_contents:
                continue

            stripped = line.strip()
            # Stop at next form section
            if re.match(r"^(\d+\.\s*WINE\s*VINTAGE|PART\s|Under\s)", stripped):
                break

            nc_match = _NC_PATTERN.match(stripped)
            if nc_match:
                nc_values.append(nc_match.group(1).strip())
                # ABV is the number after the net contents on the FIRST line
                if abv is None:
                    remainder = stripped[nc_match.end():].strip()
                    # Skip additional net contents values in compound expressions
                    # (e.g. "1 QT. 8 FL. OZ. ..." — "8 FL. OZ." is more net contents)
                    while True:
                        more_nc = _NC_PATTERN.match(remainder)
                        if more_nc:
                            remainder = remainder[more_nc.end():].strip()
                        else:
                            break
                    # Strip parenthetical annotations like "(SAKE only)"
                    remainder = re.sub(r"\([^)]*\)", "", remainder).strip()
                    # Match ABV: single value or range (e.g. "15-16")
                    abv_match = re.match(r"(\d+\.?\d*)(?:%|\s*-\s*\d+\.?\d*)?\b", remainder)
                    if abv_match:
                        abv = abv_match.group(1)
            elif not nc_values:
                # First data line might have net contents somewhere in it
                nc_search = _NC_PATTERN.search(stripped)
                if nc_search:
                    nc_values.append(nc_search.group(1).strip())
                    remainder = stripped[nc_search.end():].strip()
                    remainder = re.sub(r"\([^)]*\)", "", remainder).strip()
                    abv_match = re.match(r"(\d+\.?\d*)(?:%|\s*-\s*\d+\.?\d*)?\b", remainder)
                    if abv_match:
                        abv = abv_match.group(1)

        # Fallback: search all collected content lines for ABV with % sign
        # (handles cases like "3.6% IF ON LABEL" embedded in complex lines)
        if abv is None and in_contents:
            for line in lines:
                pct_match = re.search(r"(\d+\.?\d*)%", line)
                if pct_match and "NET CONTENTS" not in line:
                    abv = pct_match.group(1)
                    break

        # For compound net contents (e.g. "1 QT. 8 FL. OZ. (40 FL. OZ.)"),
        # prefer the parenthetical total if it contains a recognized unit.
        # The parenthetical may span lines in pdfplumber output.
        if nc_values:
            full_nc_text = " ".join(lines)
            # Match "(40 FL. OZ.)" even when split across lines with intervening text
            paren_nc = re.search(
                r"\((\d+\.?\d*)\s*FL.*?OZ\s*\.?\)",
                full_nc_text, re.IGNORECASE,
            )
            if paren_nc:
                nc_values = [f"{paren_nc.group(1)} FL. OZ"]

        net_contents = "\n".join(nc_values) if nc_values else None
        return (net_contents, abv)

    def _extract_label_images(self, pdf_bytes: bytes) -> list[LabelImage]:
        """Extract embedded label images from pages 2+ via PyMuPDF."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Failed to extract images: {e}") from e

        if len(doc) < 2:
            doc.close()
            return []

        # Extract image type annotations per page
        image_types_by_page = self._extract_image_type_annotations(pdf_bytes)

        label_images = []
        img_index = 0

        for page_num in range(1, len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)

            # Collect qualifying XObject images for this page
            page_images: list[bytes] = []
            had_signature = False
            for img_info in images:
                xref = img_info[0]
                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    continue

                img_bytes = extracted["image"]
                width = extracted["width"]
                height = extracted["height"]

                # Filter out tiny images (logos, icons, signatures)
                if (
                    len(img_bytes) < _MIN_IMAGE_BYTES
                    or width < _MIN_IMAGE_DIM
                    or height < _MIN_IMAGE_DIM
                ):
                    continue

                # Filter TTB officer signature images: thin wide strips that
                # are mostly white/grayscale (handwriting on white background).
                # Real label strips (neck bands, back labels) have color content.
                short_side = min(width, height)
                long_side = max(width, height)
                if short_side < 200 and long_side / short_side > 3.0:
                    if _is_signature_image(img_bytes):
                        had_signature = True
                        continue

                page_images.append(img_bytes)

            # Pixmap fallback: render full page as PNG when no XObject images
            # but ONLY if the page has Image Type annotations (label page).
            # Pages with no images and no annotations are form/certificate
            # pages -- skip them.
            # Also skip if we just filtered a signature: the page is a
            # certificate/approval page, not a label page.
            if not page_images:
                if page_num not in image_types_by_page:
                    continue
                if had_signature:
                    continue
                pixmap = page.get_pixmap(dpi=150)
                png_bytes = pixmap.tobytes("png")
                # Skip mostly-blank pages (metadata-only pages that list
                # "Image Type:" + "Actual Dimensions:" but have no label)
                if _is_signature_image(png_bytes, white_threshold=0.90):
                    continue
                page_images = [png_bytes]

            page_annotations = image_types_by_page.get(page_num, [])
            for ann_idx, img_bytes in enumerate(page_images):
                if ann_idx < len(page_annotations):
                    raw_type = page_annotations[ann_idx]
                    panel_type = _classify_panel(raw_type)
                else:
                    raw_type = f"label_{img_index + 1}"
                    panel_type = "front" if img_index == 0 else "other"

                label_images.append(
                    LabelImage(
                        image_bytes=img_bytes,
                        panel_type=panel_type,
                        image_type_raw=raw_type,
                    )
                )
                img_index += 1

        doc.close()
        return label_images

    # Form/certificate page markers -- pages with these are NOT label pages
    # even if they contain "Image Type:" annotations.
    _FORM_BOILERPLATE = (
        "PREVIOUS EDITIONS ARE OBSOLETE",
        "AUTHORIZED SIGNATURE",
    )

    def _extract_image_type_annotations(self, pdf_bytes: bytes) -> dict[int, list[str]]:
        """Extract 'Image Type:' text annotations from pages 2+.

        Returns a dict mapping page number (0-indexed from doc start) to
        the list of annotation strings found on that page.

        Pages containing form boilerplate (signature/certificate pages) are
        excluded even if they contain Image Type annotations.
        """
        types_by_page: dict[int, list[str]] = {}
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception:
            return types_by_page

        for page in pdf.pages[1:]:
            text = page.extract_text() or ""

            # Skip form/certificate pages (may have Image Type text but no labels)
            if any(marker in text for marker in self._FORM_BOILERPLATE):
                continue

            page_types = [
                match.group(1).strip()
                for match in re.finditer(r"Image Type:\n(.+?)(?:\n|$)", text)
            ]
            if page_types:
                types_by_page[page.page_number - 1] = page_types
        pdf.close()
        return types_by_page
