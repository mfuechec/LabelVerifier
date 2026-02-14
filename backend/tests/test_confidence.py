from app.services.comparison import ConfidenceScorer
from app.models.schemas import FieldComparisonResult


class TestConfidenceScorer:
    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_all_match_high_confidence(self):
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="class_type", status="match",
                confidence=95.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="government_warning", status="match",
                confidence=100.0, match_strategy="exact"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert overall >= 90.0
        assert status == "pass"

    def test_mixed_scores_needs_review(self):
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=95.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="class_type", status="match",
                confidence=60.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="government_warning", status="match",
                confidence=80.0, match_strategy="exact"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert 70 <= overall < 90
        assert status == "needs_review"

    def test_field_missing_is_fail(self):
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="government_warning", status="field_missing",
                confidence=0.0, match_strategy="exact"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert status == "fail"

    def test_content_mismatch_is_fail(self):
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="alcohol_content", status="content_mismatch",
                confidence=20.0, match_strategy="numeric"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert status == "fail"

    def test_empty_fields(self):
        overall, status = self.scorer.calculate([])
        assert overall == 0.0
        assert status == "fail"
