"""Tests for the evaluation framework's pure functions."""

import pytest
from unittest.mock import MagicMock

from evals.run_eval import (
    compare_field,
    normalize_for_comparison,
    build_field_assertions,
    aggregate_summary,
    FieldAssertion,
    ProductResult,
    EvalSummary,
)
from app.models.schemas import (
    FieldComparisonResult,
    ProcessingStats,
    ReviewSummary,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# normalize_for_comparison (kept from v1)
# ---------------------------------------------------------------------------


class TestNormalizeForComparison:

    def test_none_returns_empty(self):
        assert normalize_for_comparison(None) == ""

    def test_strips_whitespace(self):
        assert normalize_for_comparison("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert normalize_for_comparison("hello   world") == "hello world"

    def test_lowercases(self):
        assert normalize_for_comparison("HELLO World") == "hello world"

    def test_handles_newlines_and_tabs(self):
        assert normalize_for_comparison("line1\n\tline2") == "line1 line2"


# ---------------------------------------------------------------------------
# compare_field (kept from v1)
# ---------------------------------------------------------------------------


class TestCompareField:

    def test_both_none_is_correct(self):
        correct, similarity = compare_field(None, None)
        assert correct is True
        assert similarity == 100.0

    def test_expected_none_extracted_present(self):
        correct, similarity = compare_field(None, "some value")
        assert correct is False
        assert similarity == 0.0

    def test_expected_present_extracted_none(self):
        correct, similarity = compare_field("some value", None)
        assert correct is False
        assert similarity == 0.0

    def test_exact_match(self):
        correct, similarity = compare_field("Jagermeister", "Jagermeister")
        assert correct is True
        assert similarity == 100.0

    def test_case_insensitive_match(self):
        correct, similarity = compare_field("HELLO", "hello")
        assert correct is True

    def test_whitespace_insensitive_match(self):
        correct, similarity = compare_field("New  York", "New York")
        assert correct is True

    def test_fuzzy_match_above_threshold(self):
        correct, _ = compare_field("Jagermeister", "Jagermeister Liqueur")
        # token_set_ratio should handle the subset relationship
        assert correct is True

    def test_clearly_different_values(self):
        correct, similarity = compare_field("Vodka", "Whiskey")
        assert correct is False
        assert similarity < 85


# ---------------------------------------------------------------------------
# build_field_assertions
# ---------------------------------------------------------------------------

def _make_verification_result(fields: list[FieldComparisonResult]) -> VerificationResult:
    """Helper to build a minimal VerificationResult."""
    return VerificationResult(
        session_id="test-session",
        status="pass",
        overall_confidence=95.0,
        beverage_type="distilled_spirits",
        fields=fields,
        annotated_images={},
        created_at="2026-01-01T00:00:00Z",
        review_summary=ReviewSummary(
            total_fields=len(fields),
            fields_needing_review=0,
            fields_reviewed=0,
            flagged_field_names=[],
        ),
        processing_stats=ProcessingStats(),
    )


class TestBuildFieldAssertions:

    def test_matching_field(self):
        result = _make_verification_result([
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="Vodka",
                extracted_value="Vodka",
                status="match",
                confidence=100.0,
                match_strategy="fuzzy",
            ),
        ])
        assertions = build_field_assertions({"brand_name": "match"}, result)
        assert len(assertions) == 1
        assert assertions[0].correct is True
        assert assertions[0].expected_status == "match"
        assert assertions[0].actual_status == "match"

    def test_mismatching_field_status(self):
        result = _make_verification_result([
            FieldComparisonResult(
                field_name="government_warning",
                declared_value=None,
                extracted_value="GOVERNMENT WARNING: ...",
                status="content_mismatch",
                confidence=40.0,
                match_strategy="exact",
            ),
        ])
        assertions = build_field_assertions({"government_warning": "match"}, result)
        assert len(assertions) == 1
        assert assertions[0].correct is False
        assert assertions[0].expected_status == "match"
        assert assertions[0].actual_status == "content_mismatch"

    def test_field_missing_from_pipeline(self):
        """If expected field not in pipeline result, assertion is incorrect."""
        result = _make_verification_result([])
        assertions = build_field_assertions({"sulfites_declaration": "match"}, result)
        assert len(assertions) == 1
        assert assertions[0].correct is False
        assert assertions[0].actual_status is None

    def test_multiple_fields(self):
        result = _make_verification_result([
            FieldComparisonResult(
                field_name="brand_name", status="match",
                confidence=100.0, match_strategy="fuzzy",
            ),
            FieldComparisonResult(
                field_name="alcohol_content", status="content_mismatch",
                confidence=50.0, match_strategy="numeric",
            ),
        ])
        expected = {
            "brand_name": "match",
            "alcohol_content": "match",
        }
        assertions = build_field_assertions(expected, result)
        assert len(assertions) == 2
        brand = next(a for a in assertions if a.field_name == "brand_name")
        alc = next(a for a in assertions if a.field_name == "alcohol_content")
        assert brand.correct is True
        assert alc.correct is False


# ---------------------------------------------------------------------------
# aggregate_summary
# ---------------------------------------------------------------------------


class TestAggregateSummary:

    def _make_product_result(
        self, product_id, expected, actual, field_assertions=None, cost=0.01, error=None,
    ):
        return ProductResult(
            product_id=product_id,
            expected_status=expected,
            actual_status=actual,
            status_correct=(expected == actual),
            field_assertions=field_assertions or [],
            cost_usd=cost,
            total_time_ms=1000,
            llm_calls=3,
            error=error,
        )

    def test_empty_results(self):
        summary = aggregate_summary([])
        assert summary.total_products == 0
        assert summary.status_accuracy == 0.0

    def test_single_correct_product(self):
        results = [
            self._make_product_result(
                "test-1", "pass", "pass",
                field_assertions=[
                    FieldAssertion("brand_name", "match", "match", True),
                ],
            ),
        ]
        summary = aggregate_summary(results)
        assert summary.total_products == 1
        assert summary.products_evaluated == 1
        assert summary.status_correct == 1
        assert summary.status_accuracy == 1.0
        assert summary.field_assertions_total == 1
        assert summary.field_assertions_correct == 1
        assert summary.field_accuracy == 1.0

    def test_mixed_results(self):
        results = [
            self._make_product_result("a", "pass", "pass", [
                FieldAssertion("brand_name", "match", "match", True),
            ]),
            self._make_product_result("b", "fail", "needs_review", [
                FieldAssertion("brand_name", "match", "content_mismatch", False),
            ]),
        ]
        summary = aggregate_summary(results)
        assert summary.products_evaluated == 2
        assert summary.status_correct == 1
        assert summary.status_accuracy == 0.5
        assert summary.field_assertions_correct == 1
        assert summary.field_assertions_total == 2

    def test_errored_products_excluded(self):
        results = [
            self._make_product_result("a", "pass", "pass", cost=0.02),
            self._make_product_result("b", "pass", "error", error="Image not found"),
        ]
        summary = aggregate_summary(results)
        assert summary.products_evaluated == 1
        assert summary.products_errored == 1
        assert summary.total_cost_usd == 0.02

    def test_confusion_matrix(self):
        results = [
            self._make_product_result("a", "pass", "fail"),
            self._make_product_result("b", "pass", "fail"),
            self._make_product_result("c", "fail", "pass"),
        ]
        summary = aggregate_summary(results)
        assert summary.status_confusion["pass"]["fail"] == 2
        assert summary.status_confusion["fail"]["pass"] == 1

    def test_field_accuracy_by_name(self):
        results = [
            self._make_product_result("a", "pass", "pass", [
                FieldAssertion("brand_name", "match", "match", True),
                FieldAssertion("alcohol_content", "match", "content_mismatch", False),
            ]),
            self._make_product_result("b", "pass", "pass", [
                FieldAssertion("brand_name", "match", "match", True),
                FieldAssertion("alcohol_content", "match", "match", True),
            ]),
        ]
        summary = aggregate_summary(results)
        assert summary.field_accuracy_by_name["brand_name"] == {"total": 2, "correct": 2}
        assert summary.field_accuracy_by_name["alcohol_content"] == {"total": 2, "correct": 1}

    def test_cost_aggregation(self):
        results = [
            self._make_product_result("a", "pass", "pass", cost=0.05),
            self._make_product_result("b", "pass", "pass", cost=0.03),
        ]
        summary = aggregate_summary(results)
        assert abs(summary.total_cost_usd - 0.08) < 0.001
        assert abs(summary.avg_cost_per_product - 0.04) < 0.001
