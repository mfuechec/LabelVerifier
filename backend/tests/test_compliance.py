from app.services.compliance import ComplianceChecker


class TestComplianceChecker:
    def setup_method(self):
        self.checker = ComplianceChecker()

    def test_spirits_all_fields_present(self):
        extracted = {
            "brand_name": "Test",
            "class_type": "Bourbon",
            "alcohol_content": "45%",
            "net_contents": "750 mL",
            "producer_name": "Distillery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = self.checker.check_compliance(extracted, "distilled_spirits")
        assert len(issues) == 0

    def test_spirits_missing_warning(self):
        extracted = {
            "brand_name": "Test",
            "class_type": "Bourbon",
            "alcohol_content": "45%",
            "net_contents": "750 mL",
            "producer_name": "Distillery",
        }
        issues = self.checker.check_compliance(extracted, "distilled_spirits")
        field_names = [i.field_name for i in issues]
        assert "government_warning" in field_names

    def test_beer_missing_abv_is_needs_review(self):
        extracted = {
            "brand_name": "Test Beer",
            "class_type": "Ale",
            "net_contents": "355 mL",
            "producer_name": "Brewery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = self.checker.check_compliance(extracted, "beer")
        abv_issues = [i for i in issues if i.field_name == "alcohol_content"]
        assert len(abv_issues) == 1
        assert abv_issues[0].severity == "needs_review"

    def test_wine_missing_sulfites_when_required(self):
        extracted = {
            "brand_name": "Test Wine",
            "class_type": "Red Wine",
            "alcohol_content": "14%",
            "net_contents": "750 mL",
            "producer_name": "Winery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = self.checker.check_compliance(
            extracted, "wine", requires_sulfites=True
        )
        field_names = [i.field_name for i in issues]
        assert "sulfites_declaration" in field_names

    def test_imported_missing_country_of_origin(self):
        extracted = {
            "brand_name": "Test",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Distillery",
            "government_warning": "GOVERNMENT WARNING: ...",
        }
        issues = self.checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        field_names = [i.field_name for i in issues]
        assert "country_of_origin" in field_names

    def test_imported_with_country_of_origin(self):
        extracted = {
            "brand_name": "Test",
            "class_type": "Vodka",
            "alcohol_content": "40%",
            "net_contents": "750 mL",
            "producer_name": "Distillery",
            "government_warning": "GOVERNMENT WARNING: ...",
            "country_of_origin": "Russia",
        }
        issues = self.checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        field_names = [i.field_name for i in issues]
        assert "country_of_origin" not in field_names
