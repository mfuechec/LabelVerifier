import io
import re

import pdfplumber

from app.models.schemas import ApplicationData


# Maps PDF label text to ApplicationData field names
_FIELD_MAP = {
    "Application ID": "application_id",
    "Brand Name": "brand_name",
    "Class/Type": "class_type",
    "Alcohol Content": "alcohol_content",
    "Net Contents": "net_contents",
    "Producer Name": "producer_name",
    "Producer Address": "producer_address",
    "Country of Origin": "country_of_origin",
    "Importer Name": "importer_name",
    "Importer Address": "importer_address",
    "Beverage Type": "beverage_type",
    "Sulfites Declared": "has_sulfites_declaration",
}

_BEVERAGE_TYPE_MAP = {
    "distilled spirits": "distilled_spirits",
    "wine": "wine",
    "beer": "beer",
}


class PDFApplicationParser:
    def parse_application_pdf(self, pdf_bytes: bytes) -> ApplicationData:
        if not pdf_bytes:
            raise ValueError("Failed to parse PDF: empty input")

        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {e}") from e

        text = ""
        for page in pdf.pages:
            text += page.extract_text() or ""
        pdf.close()

        if not text.strip():
            raise ValueError("Failed to parse PDF: no text content found")

        parsed = self._extract_fields(text)
        return self._build_application_data(parsed)

    def _extract_fields(self, text: str) -> dict[str, str | None]:
        fields: dict[str, str | None] = {}

        for pdf_label, field_name in _FIELD_MAP.items():
            pattern = re.escape(pdf_label) + r":\s*(.+)"
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                fields[field_name] = None if value == "--" else value
            else:
                fields[field_name] = None

        return fields

    def _build_application_data(self, fields: dict[str, str | None]) -> ApplicationData:
        # Map beverage type display name to enum value
        bev_raw = fields.get("beverage_type") or ""
        beverage_type = _BEVERAGE_TYPE_MAP.get(bev_raw.lower(), "distilled_spirits")

        # Map sulfites to bool
        sulfites_raw = fields.get("has_sulfites_declaration") or "No"
        has_sulfites = sulfites_raw.lower() == "yes"

        return ApplicationData(
            application_id=fields.get("application_id"),
            brand_name=fields.get("brand_name") or "",
            class_type=fields.get("class_type") or "",
            alcohol_content=fields.get("alcohol_content") or "",
            net_contents=fields.get("net_contents") or "",
            producer_name=fields.get("producer_name"),
            producer_address=fields.get("producer_address"),
            country_of_origin=fields.get("country_of_origin"),
            importer_name=fields.get("importer_name"),
            importer_address=fields.get("importer_address"),
            beverage_type=beverage_type,
            has_sulfites_declaration=has_sulfites,
        )
