"""Tests for the evaluation framework's pure functions."""

import pytest
from evals.run_eval import (
    compare_field,
    normalize_for_comparison,
    aggregate_stats,
    EvalResults,
    FieldResult,
    LabelResult,
    EVAL_FIELDS,
)


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


class TestAggregateStats:

    def _make_result(self, field_results, label_id="test-001", error=None):
        return LabelResult(
            label_id=label_id,
            image_path="/fake/path.jpg",
            field_results=field_results,
            extraction_error=error,
        )

    def test_counts_successful_and_failed(self):
        results = EvalResults(total_labels=2)
        results.label_results = [
            self._make_result([], label_id="ok"),
            self._make_result([], label_id="fail", error="boom"),
        ]
        aggregate_stats(results)
        assert results.successful_extractions == 1
        assert results.failed_extractions == 1

    def test_true_positive(self):
        """Expected present, extracted correct -> true positive."""
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", "Vodka", "Vodka", True, 100.0, "high"),
            ])
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.true_positives == 1
        assert stats.correct == 1

    def test_false_positive(self):
        """Expected null, extracted a value -> false positive."""
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", None, "Hallucinated", False, 0.0, "high"),
            ])
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.false_positives == 1
        assert stats.correct == 0

    def test_false_negative(self):
        """Expected present, extracted nothing -> false negative."""
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", "Vodka", None, False, 0.0, "low"),
            ])
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.false_negatives == 1

    def test_true_negative(self):
        """Expected null, extracted null -> true negative."""
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", None, None, True, 100.0, "high"),
            ])
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.true_negatives == 1
        assert stats.correct == 1

    def test_content_mismatch(self):
        """Expected present, extracted wrong value -> content mismatch (not false negative)."""
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", "Vodka", "Whiskey", False, 30.0, "high"),
            ])
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.content_mismatches == 1
        assert stats.false_negatives == 0
        assert stats.false_positives == 0
        assert stats.correct == 0

    def test_confidence_calibration(self):
        results = EvalResults(total_labels=1)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", "A", "A", True, 100.0, "high"),
                FieldResult("class_type", "B", "B", True, 100.0, "medium"),
                FieldResult("net_contents", "C", "Wrong", False, 20.0, "low"),
            ])
        ]
        aggregate_stats(results)
        assert results.field_stats["brand_name"].high_conf_correct == 1
        assert results.field_stats["brand_name"].high_conf_total == 1
        assert results.field_stats["class_type"].medium_conf_correct == 1
        assert results.field_stats["class_type"].medium_conf_total == 1
        assert results.field_stats["net_contents"].low_conf_correct == 0
        assert results.field_stats["net_contents"].low_conf_total == 1

    def test_accuracy_precision_recall(self):
        """Verify computed metrics from aggregate counts."""
        results = EvalResults(total_labels=2)
        results.label_results = [
            self._make_result([
                FieldResult("brand_name", "A", "A", True, 100.0, "high"),
            ], label_id="1"),
            self._make_result([
                FieldResult("brand_name", "B", None, False, 0.0, "low"),
            ], label_id="2"),
        ]
        aggregate_stats(results)
        stats = results.field_stats["brand_name"]
        assert stats.accuracy == 0.5  # 1 correct / 2 total
        assert stats.precision == 1.0  # 1 TP / (1 TP + 0 FP)
        assert stats.recall == 0.5  # 1 TP / (1 TP + 1 FN)
