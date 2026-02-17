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

    def test_critical_field_missing_is_fail(self):
        """Critical field (government_warning) missing should always fail."""
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

    def test_critical_content_mismatch_is_fail(self):
        """Critical field (alcohol_content) content_mismatch should fail."""
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

    def test_noncritical_mismatch_is_needs_review(self):
        """Non-critical field (producer_address) mismatch should NOT auto-fail."""
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="class_type", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="government_warning", status="match",
                confidence=100.0, match_strategy="exact"
            ),
            FieldComparisonResult(
                field_name="alcohol_content", status="match",
                confidence=100.0, match_strategy="numeric"
            ),
            FieldComparisonResult(
                field_name="net_contents", status="match",
                confidence=100.0, match_strategy="numeric"
            ),
            FieldComparisonResult(
                field_name="producer_address", status="content_mismatch",
                confidence=40.0, match_strategy="fuzzy"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert status == "needs_review"

    def test_extraction_uncertain_triggers_needs_review(self):
        """Any extraction_uncertain field should trigger needs_review (not pass)."""
        fields = [
            FieldComparisonResult(
                field_name="brand_name", status="extraction_uncertain",
                confidence=50.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="class_type", status="match",
                confidence=100.0, match_strategy="fuzzy"
            ),
            FieldComparisonResult(
                field_name="government_warning", status="match",
                confidence=100.0, match_strategy="exact"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        assert status == "needs_review"

    def test_weighted_average_calculation(self):
        """Verify weighted average uses FIELD_WEIGHTS."""
        fields = [
            FieldComparisonResult(
                field_name="government_warning", status="match",
                confidence=100.0, match_strategy="exact"
            ),
            FieldComparisonResult(
                field_name="producer_address", status="match",
                confidence=50.0, match_strategy="fuzzy"
            ),
        ]
        overall, status = self.scorer.calculate(fields)
        # gov_warning weight=2.0, producer_address weight=0.5
        # weighted avg = (100*2.0 + 50*0.5) / (2.0+0.5) = 225/2.5 = 90.0
        assert abs(overall - 90.0) < 0.1
        assert status == "pass"

    def test_empty_fields(self):
        overall, status = self.scorer.calculate([])
        assert overall == 0.0
        assert status == "fail"
