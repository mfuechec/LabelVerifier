from dataclasses import dataclass


@dataclass
class ComplianceIssue:
    field_name: str
    severity: str  # "fail" or "needs_review"
    message: str


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
            if field not in extracted_fields or not extracted_fields[field]:
                issues.append(
                    ComplianceIssue(
                        field_name=field,
                        severity="fail",
                        message=f"Required field '{field}' is missing from the label",
                    )
                )

        # Beer ABV: flag absence as needs_review, not fail
        if beverage_type == "beer":
            if "alcohol_content" not in extracted_fields or not extracted_fields.get("alcohol_content"):
                issues.append(
                    ComplianceIssue(
                        field_name="alcohol_content",
                        severity="needs_review",
                        message="ABV not found on beer label - may be required",
                    )
                )

        # Imported products need country of origin
        if is_imported:
            if "country_of_origin" not in extracted_fields or not extracted_fields.get("country_of_origin"):
                issues.append(
                    ComplianceIssue(
                        field_name="country_of_origin",
                        severity="fail",
                        message="Country of origin is required for imported products",
                    )
                )

        # Sulfites declaration for wine
        if requires_sulfites:
            if "sulfites_declaration" not in extracted_fields or not extracted_fields.get("sulfites_declaration"):
                issues.append(
                    ComplianceIssue(
                        field_name="sulfites_declaration",
                        severity="fail",
                        message="Sulfites declaration required but not found",
                    )
                )

        return issues
