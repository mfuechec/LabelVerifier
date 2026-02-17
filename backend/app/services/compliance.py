from dataclasses import dataclass


@dataclass
class ComplianceIssue:
    field_name: str
    severity: str  # "fail" or "needs_review"
    message: str


# Human-readable field labels for compliance messages
FIELD_LABELS = {
    "brand_name": "Brand name",
    "class_type": "Class/type designation",
    "alcohol_content": "Alcohol content (ABV)",
    "net_contents": "Net contents",
    "producer_name": "Producer/bottler name",
    "government_warning": "Government health warning",
    "country_of_origin": "Country of origin",
    "sulfites_declaration": "Sulfites declaration",
    "importer_name": "Importer name",
}


class ComplianceChecker:
    """Validates mandatory field presence by beverage type."""

    MANDATORY_FIELDS = {
        "distilled_spirits": [
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "producer_name",
            "government_warning",
        ],
        "wine": [
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "producer_name",
            "government_warning",
        ],
        "beer": [
            "brand_name",
            "class_type",
            "net_contents",
            "producer_name",
            "government_warning",
        ],
    }

    # Regulatory citations per field
    FIELD_CITATIONS = {
        "brand_name": "27 CFR 5.63/4.32/7.63",
        "class_type": "27 CFR 5.63/4.32/7.63",
        "alcohol_content": "27 CFR 5.63/4.32/7.63",
        "net_contents": "27 CFR 5.63/4.32/7.63",
        "producer_name": "27 CFR 5.63/4.32/7.63",
        "government_warning": "27 CFR Part 16",
        "country_of_origin": "19 CFR 134",
        "sulfites_declaration": "27 CFR 4.32(e)",
    }

    def check_compliance(
        self,
        extracted_fields: dict[str, str | None],
        beverage_type: str,
        is_imported: bool = False,
        requires_sulfites: bool = False,
    ) -> list[ComplianceIssue]:
        issues = []

        mandatory = self.MANDATORY_FIELDS.get(beverage_type, [])

        for field in mandatory:
            # For imports, importer satisfies the producer requirement (27 CFR 5.63)
            if field == "producer_name" and is_imported and extracted_fields.get("importer_name"):
                continue
            if field not in extracted_fields or not extracted_fields[field]:
                label = FIELD_LABELS.get(field, field)
                citation = self.FIELD_CITATIONS.get(field, "")
                issues.append(
                    ComplianceIssue(
                        field_name=field,
                        severity="fail",
                        message=f"{label} is required on all alcohol labels ({citation})",
                    )
                )

        # Beer ABV: flag absence as needs_review, not fail
        if beverage_type == "beer":
            if "alcohol_content" not in extracted_fields or not extracted_fields.get("alcohol_content"):
                issues.append(
                    ComplianceIssue(
                        field_name="alcohol_content",
                        severity="needs_review",
                        message="ABV is not required on beer labels but its absence should be verified (27 CFR 7.65)",
                    )
                )

        # Imported products need country of origin
        if is_imported:
            if "country_of_origin" not in extracted_fields or not extracted_fields.get("country_of_origin"):
                issues.append(
                    ComplianceIssue(
                        field_name="country_of_origin",
                        severity="fail",
                        message="Country of origin is required for imported products (19 CFR 134)",
                    )
                )

        # Sulfites declaration for wine
        if requires_sulfites:
            if "sulfites_declaration" not in extracted_fields or not extracted_fields.get("sulfites_declaration"):
                issues.append(
                    ComplianceIssue(
                        field_name="sulfites_declaration",
                        severity="fail",
                        message="Sulfites declaration is required when sulfite content >= 10 ppm (27 CFR 4.32(e))",
                    )
                )

        return issues
