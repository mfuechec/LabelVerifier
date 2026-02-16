"""Tests for ConfidenceScorer."""

import pytest
from app.models.schemas import FieldComparisonResult
from app.services.comparison import ConfidenceScorer


@pytest.fixture
def scorer():
    return ConfidenceScorer()


def _field(name, status="match", confidence=100.0):
    return FieldComparisonResult(
        field_name=name,
        status=status,
        confidence=confidence,
        match_strategy="test",
    )


class TestConfidenceScorer:
    def test_all_match_passes(self, scorer):
        fields = [
            _field("brand_name"),
            _field("class_type"),
            _field("alcohol_content"),
            _field("net_contents"),
            _field("government_warning"),
        ]
        score, status = scorer.calculate(fields)
        assert status == "pass"
        assert score >= 90.0

    def test_critical_field_missing_fails(self, scorer):
        fields = [
            _field("brand_name"),
            _field("government_warning", "field_missing", 0.0),
            _field("alcohol_content"),
            _field("net_contents"),
        ]
        _, status = scorer.calculate(fields)
        assert status == "fail"

    def test_critical_field_mismatch_fails(self, scorer):
        fields = [
            _field("brand_name", "content_mismatch", 30.0),
            _field("alcohol_content"),
            _field("net_contents"),
            _field("government_warning"),
        ]
        _, status = scorer.calculate(fields)
        assert status == "fail"

    def test_uncertain_needs_review(self, scorer):
        fields = [
            _field("brand_name", "extraction_uncertain", 50.0),
            _field("alcohol_content"),
            _field("net_contents"),
            _field("government_warning"),
        ]
        _, status = scorer.calculate(fields)
        assert status == "needs_review"

    def test_noncritical_missing_needs_review(self, scorer):
        fields = [
            _field("brand_name"),
            _field("alcohol_content"),
            _field("net_contents"),
            _field("government_warning"),
            _field("producer_address", "field_missing", 0.0),
        ]
        score, status = scorer.calculate(fields)
        assert status == "needs_review"

    def test_empty_fields_fails(self, scorer):
        score, status = scorer.calculate([])
        assert status == "fail"
        assert score == 0.0

    def test_weighted_scoring(self, scorer):
        """Government warning has higher weight than producer address."""
        fields_warning_bad = [
            _field("government_warning", "content_mismatch", 0.0),
            _field("brand_name"),
        ]
        fields_addr_bad = [
            _field("producer_address", "content_mismatch", 0.0),
            _field("brand_name"),
        ]
        score_warning, _ = scorer.calculate(fields_warning_bad)
        score_addr, _ = scorer.calculate(fields_addr_bad)
        # Warning has weight 2.0, address 0.5 -- so warning failure drops score more
        assert score_warning < score_addr

    def test_low_average_needs_review_or_fail(self, scorer):
        """All match but low confidence scores."""
        fields = [
            _field("brand_name", "match", 70.0),
            _field("alcohol_content", "match", 70.0),
            _field("net_contents", "match", 70.0),
            _field("government_warning", "match", 70.0),
        ]
        score, status = scorer.calculate(fields)
        assert status == "needs_review"

    def test_high_average_passes(self, scorer):
        fields = [
            _field("brand_name", "match", 95.0),
            _field("alcohol_content", "match", 95.0),
            _field("net_contents", "match", 95.0),
            _field("government_warning", "match", 95.0),
        ]
        score, status = scorer.calculate(fields)
        assert status == "pass"
        assert score >= 90.0
