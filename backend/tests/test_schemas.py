import pytest
from pydantic import ValidationError
from app.models.schemas import (
    ApplicationData,
    FieldComparisonResult,
    VerificationResult,
    BoundingBox,
    OverrideRequest,
    DecisionRequest,
    FeedbackRequest,
)


class TestApplicationData:
    def test_valid_spirits_application(self):
        data = ApplicationData(
            application_id="APP-001",
            brand_name="Test Brand",
            class_type="Bourbon Whiskey",
            alcohol_content="45%",
            net_contents="750 mL",
            producer_name="Test Distillery",
            producer_address="Louisville, KY",
            beverage_type="distilled_spirits",
        )
        assert data.brand_name == "Test Brand"
        assert data.beverage_type == "distilled_spirits"

    def test_valid_wine_application(self):
        data = ApplicationData(
            application_id="APP-002",
            brand_name="Test Wine",
            class_type="Red Wine",
            alcohol_content="14.5%",
            net_contents="750 mL",
            beverage_type="wine",
            has_sulfites_declaration=True,
            country_of_origin="Italy",
            importer_name="Wine Imports LLC",
            importer_address="Chicago, IL",
        )
        assert data.has_sulfites_declaration is True

    def test_invalid_beverage_type(self):
        with pytest.raises(ValidationError):
            ApplicationData(
                application_id="APP-003",
                brand_name="Test",
                class_type="Test",
                alcohol_content="5%",
                net_contents="355 mL",
                beverage_type="soda",
            )

    def test_optional_fields_default_none(self):
        data = ApplicationData(
            application_id="APP-004",
            brand_name="Test",
            class_type="Test",
            alcohol_content="5%",
            net_contents="355 mL",
            beverage_type="beer",
        )
        assert data.country_of_origin is None
        assert data.importer_name is None
        assert data.has_sulfites_declaration is False


class TestFieldComparisonResult:
    def test_valid_match(self):
        result = FieldComparisonResult(
            field_name="brand_name",
            declared_value="Test Brand",
            extracted_value="Test Brand",
            status="match",
            confidence=95.0,
            match_strategy="fuzzy",
        )
        assert result.status == "match"

    def test_with_bounding_box(self):
        result = FieldComparisonResult(
            field_name="brand_name",
            declared_value="Test",
            extracted_value="Test",
            status="match",
            confidence=100.0,
            match_strategy="fuzzy",
            bounding_box=BoundingBox(panel="front", x=10, y=20, width=100, height=50),
        )
        assert result.bounding_box.panel == "front"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="Test",
                extracted_value="Test",
                status="invalid_status",
                confidence=100.0,
                match_strategy="fuzzy",
            )


class TestVerificationResult:
    def test_valid_result(self):
        result = VerificationResult(
            session_id="uuid-1",
            status="pass",
            overall_confidence=95.0,
            beverage_type="distilled_spirits",
            fields=[],
            annotated_images={},
            created_at="2026-02-14T10:00:00Z",
        )
        assert result.status == "pass"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            VerificationResult(
                session_id="uuid-1",
                status="unknown",
                overall_confidence=95.0,
                beverage_type="distilled_spirits",
                fields=[],
                annotated_images={},
                created_at="2026-02-14T10:00:00Z",
            )


class TestOverrideRequest:
    def test_valid_override(self):
        req = OverrideRequest(override_status="match", note="Looks correct to me")
        assert req.override_status == "match"

    def test_invalid_override_status(self):
        with pytest.raises(ValidationError):
            OverrideRequest(override_status="approved")


class TestDecisionRequest:
    def test_valid_decision(self):
        req = DecisionRequest(decision="confirmed", notes="All fields match")
        assert req.decision == "confirmed"


class TestFeedbackRequest:
    def test_valid_feedback(self):
        req = FeedbackRequest(ai_correct=True)
        assert req.ai_correct is True

    def test_feedback_with_details(self):
        req = FeedbackRequest(
            ai_correct=False,
            field_name="brand_name",
            note="AI misread the brand name",
        )
        assert req.ai_correct is False
        assert req.field_name == "brand_name"
