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
    ReviewSummary,
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


class TestFieldComparisonResultNewFields:
    def test_defaults_for_new_fields(self):
        result = FieldComparisonResult(
            field_name="brand_name",
            declared_value="Test",
            extracted_value="Test",
            status="match",
            confidence=95.0,
            match_strategy="fuzzy",
        )
        assert result.extraction_confidence is None
        assert result.confidence_reason is None
        assert result.reviewed is False

    def test_with_extraction_confidence(self):
        result = FieldComparisonResult(
            field_name="brand_name",
            declared_value="Test",
            extracted_value="Test",
            status="extraction_uncertain",
            confidence=50.0,
            match_strategy="fuzzy",
            extraction_confidence="low",
            confidence_reason="Fuzzy match: 62% -- below 85% threshold | Extraction quality: low -- confidence capped at 50",
            reviewed=True,
        )
        assert result.extraction_confidence == "low"
        assert "Extraction quality: low" in result.confidence_reason
        assert result.reviewed is True

    def test_invalid_extraction_confidence(self):
        with pytest.raises(ValidationError):
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="Test",
                extracted_value="Test",
                status="match",
                confidence=95.0,
                match_strategy="fuzzy",
                extraction_confidence="invalid",
            )


class TestReviewSummary:
    def test_valid_summary(self):
        summary = ReviewSummary(
            total_fields=10,
            fields_needing_review=3,
            fields_reviewed=1,
            flagged_field_names=["brand_name", "alcohol_content", "government_warning"],
        )
        assert summary.total_fields == 10
        assert summary.fields_needing_review == 3
        assert summary.fields_reviewed == 1
        assert len(summary.flagged_field_names) == 3

    def test_empty_flagged(self):
        summary = ReviewSummary(
            total_fields=8,
            fields_needing_review=0,
            fields_reviewed=0,
            flagged_field_names=[],
        )
        assert summary.flagged_field_names == []


class TestVerificationResultWithReviewSummary:
    def test_review_summary_default_none(self):
        result = VerificationResult(
            session_id="uuid-1",
            status="pass",
            overall_confidence=95.0,
            beverage_type="distilled_spirits",
            fields=[],
            annotated_images={},
            created_at="2026-02-14T10:00:00Z",
        )
        assert result.review_summary is None

    def test_with_review_summary(self):
        summary = ReviewSummary(
            total_fields=10,
            fields_needing_review=2,
            fields_reviewed=1,
            flagged_field_names=["brand_name", "alcohol_content"],
        )
        result = VerificationResult(
            session_id="uuid-1",
            status="needs_review",
            overall_confidence=75.0,
            beverage_type="distilled_spirits",
            fields=[],
            annotated_images={},
            created_at="2026-02-14T10:00:00Z",
            review_summary=summary,
        )
        assert result.review_summary.fields_needing_review == 2


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
