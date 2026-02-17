#!/usr/bin/env python3
"""
Evaluation framework for LabelVerifier LLM extraction accuracy.

Usage:
    # Run evaluation against ground truth
    python -m evals.run_eval
    
    # Run with specific ground truth file
    python -m evals.run_eval --ground-truth path/to/ground_truth.json
    
    # Generate template entries for new images
    python -m evals.run_eval --generate-template "test data/0. Spirits Complete/*.jpg"
    
    # Run evaluation and save detailed results
    python -m evals.run_eval --output results.json
"""

import argparse
import asyncio
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rapidfuzz import fuzz

from app.config import settings
from app.services.extraction import AnthropicExtractor, GroqExtractor


# Fields to evaluate
EVAL_FIELDS = [
    "brand_name",
    "fanciful_name", 
    "class_type",
    "alcohol_content",
    "alcohol_proof",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_of_origin",
    "importer_name",
    "importer_address",
    "government_warning",
    "sulfites_declaration",
]

# Fuzzy match threshold for "correct" extraction
FUZZY_THRESHOLD = 85


@dataclass
class FieldResult:
    """Result for a single field extraction."""
    field_name: str
    expected: str | None
    extracted: str | None
    correct: bool
    similarity: float
    confidence: str  # high/medium/low from model
    

@dataclass
class LabelResult:
    """Result for a single label evaluation."""
    label_id: str
    image_path: str
    field_results: list[FieldResult]
    extraction_error: str | None = None
    

@dataclass
class FieldStats:
    """Aggregate statistics for a field across all labels."""
    field_name: str
    total: int = 0
    correct: int = 0
    present_expected: int = 0  # Expected to have a value
    present_extracted: int = 0  # Actually extracted a value
    true_positives: int = 0  # Correctly extracted when expected
    false_positives: int = 0  # Extracted when should be null
    false_negatives: int = 0  # Missed when should be present
    true_negatives: int = 0  # Correctly null when expected null
    # Confidence calibration
    high_conf_correct: int = 0
    high_conf_total: int = 0
    medium_conf_correct: int = 0
    medium_conf_total: int = 0
    low_conf_correct: int = 0
    low_conf_total: int = 0
    
    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0
    
    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator > 0 else 0.0
    
    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator > 0 else 0.0
    
    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    @property
    def high_conf_accuracy(self) -> float:
        return self.high_conf_correct / self.high_conf_total if self.high_conf_total > 0 else 0.0


@dataclass  
class EvalResults:
    """Complete evaluation results."""
    total_labels: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    field_stats: dict[str, FieldStats] = field(default_factory=dict)
    label_results: list[LabelResult] = field(default_factory=list)
    
    def __post_init__(self):
        for f in EVAL_FIELDS:
            self.field_stats[f] = FieldStats(field_name=f)


def normalize_for_comparison(text: str | None) -> str:
    """Normalize text for fuzzy comparison."""
    if text is None:
        return ""
    # Collapse whitespace, lowercase, strip
    import re
    text = re.sub(r'\s+', ' ', text.strip().lower())
    return text


def compare_field(expected: str | None, extracted: str | None) -> tuple[bool, float]:
    """Compare expected vs extracted value.
    
    Returns:
        (is_correct, similarity_score)
    """
    # Both null = correct
    if expected is None and extracted is None:
        return True, 100.0
    
    # One null, one not = incorrect
    if expected is None or extracted is None:
        return False, 0.0
    
    # Both have values - fuzzy compare
    norm_exp = normalize_for_comparison(expected)
    norm_ext = normalize_for_comparison(extracted)
    
    # Try multiple fuzzy strategies
    similarity = max(
        fuzz.ratio(norm_ext, norm_exp),
        fuzz.token_sort_ratio(norm_ext, norm_exp),
        fuzz.token_set_ratio(norm_ext, norm_exp),
    )
    
    return similarity >= FUZZY_THRESHOLD, similarity


async def run_extraction(extractor, image_path: str, panel_type: str) -> dict[str, Any]:
    """Run extraction on a single image."""
    image_bytes = Path(image_path).read_bytes()
    
    # Detect mime type
    mime_type = "image/jpeg"
    if image_path.lower().endswith(".png"):
        mime_type = "image/png"
    elif image_path.lower().endswith(".webp"):
        mime_type = "image/webp"
    
    result = await extractor.extract_fields(image_bytes, panel_type, mime_type)
    
    if result.error:
        raise RuntimeError(result.error)
    
    # Convert to simple dict of field -> value
    extracted = {}
    confidences = {}
    for field_name, field_data in result.fields.items():
        if isinstance(field_data, dict):
            extracted[field_name] = field_data.get("value")
            confidences[field_name] = field_data.get("extraction_confidence", "high")
        else:
            extracted[field_name] = field_data
            confidences[field_name] = "high"
    
    return {"fields": extracted, "confidences": confidences}


async def evaluate_label(
    extractor,
    label: dict,
    base_path: Path,
) -> LabelResult:
    """Evaluate extraction accuracy for a single label."""
    label_id = label["id"]
    image_path = base_path / label["image_path"]
    panel_type = label.get("panel_type", "front")
    expected_fields = label["expected_fields"]
    
    field_results = []
    extraction_error = None
    
    try:
        result = await run_extraction(extractor, str(image_path), panel_type)
        extracted = result["fields"]
        confidences = result["confidences"]
        
        for field_name in EVAL_FIELDS:
            expected = expected_fields.get(field_name)
            actual = extracted.get(field_name)
            confidence = confidences.get(field_name, "high")
            
            correct, similarity = compare_field(expected, actual)
            
            field_results.append(FieldResult(
                field_name=field_name,
                expected=expected,
                extracted=actual,
                correct=correct,
                similarity=similarity,
                confidence=confidence,
            ))
            
    except Exception as e:
        extraction_error = str(e)
        # Add failed results for all fields
        for field_name in EVAL_FIELDS:
            field_results.append(FieldResult(
                field_name=field_name,
                expected=expected_fields.get(field_name),
                extracted=None,
                correct=False,
                similarity=0.0,
                confidence="low",
            ))
    
    return LabelResult(
        label_id=label_id,
        image_path=str(image_path),
        field_results=field_results,
        extraction_error=extraction_error,
    )


def aggregate_stats(results: EvalResults) -> None:
    """Aggregate field-level statistics from label results."""
    for label_result in results.label_results:
        if label_result.extraction_error:
            results.failed_extractions += 1
        else:
            results.successful_extractions += 1
        
        for fr in label_result.field_results:
            stats = results.field_stats[fr.field_name]
            stats.total += 1
            
            if fr.correct:
                stats.correct += 1
            
            # Track presence
            if fr.expected is not None:
                stats.present_expected += 1
            if fr.extracted is not None:
                stats.present_extracted += 1
            
            # Confusion matrix
            if fr.expected is not None and fr.extracted is not None and fr.correct:
                stats.true_positives += 1
            elif fr.expected is None and fr.extracted is not None:
                stats.false_positives += 1
            elif fr.expected is not None and (fr.extracted is None or not fr.correct):
                stats.false_negatives += 1
            elif fr.expected is None and fr.extracted is None:
                stats.true_negatives += 1
            
            # Confidence calibration
            if fr.extracted is not None:
                if fr.confidence == "high":
                    stats.high_conf_total += 1
                    if fr.correct:
                        stats.high_conf_correct += 1
                elif fr.confidence == "medium":
                    stats.medium_conf_total += 1
                    if fr.correct:
                        stats.medium_conf_correct += 1
                elif fr.confidence == "low":
                    stats.low_conf_total += 1
                    if fr.correct:
                        stats.low_conf_correct += 1


def print_results(results: EvalResults) -> None:
    """Print evaluation results in a readable format."""
    print("\n" + "=" * 80)
    print("LABELVERIFIER EXTRACTION ACCURACY EVALUATION")
    print("=" * 80)
    
    print(f"\nTotal labels evaluated: {results.total_labels}")
    print(f"Successful extractions: {results.successful_extractions}")
    print(f"Failed extractions: {results.failed_extractions}")
    
    print("\n" + "-" * 80)
    print(f"{'Field':<25} | {'Accuracy':>8} | {'Precision':>9} | {'Recall':>6} | {'F1':>6} | {'High Conf':>9}")
    print("-" * 80)
    
    for field_name in EVAL_FIELDS:
        stats = results.field_stats[field_name]
        if stats.total == 0:
            continue
        print(
            f"{field_name:<25} | "
            f"{stats.accuracy:>7.1%} | "
            f"{stats.precision:>8.1%} | "
            f"{stats.recall:>5.1%} | "
            f"{stats.f1:>5.2f} | "
            f"{stats.high_conf_accuracy:>8.1%}"
        )
    
    print("-" * 80)
    
    # Overall accuracy
    total_correct = sum(s.correct for s in results.field_stats.values())
    total_fields = sum(s.total for s in results.field_stats.values())
    overall_accuracy = total_correct / total_fields if total_fields > 0 else 0
    print(f"{'OVERALL':<25} | {overall_accuracy:>7.1%}")
    
    # Confidence calibration summary
    print("\n" + "-" * 80)
    print("CONFIDENCE CALIBRATION")
    print("-" * 80)
    
    total_high = sum(s.high_conf_total for s in results.field_stats.values())
    correct_high = sum(s.high_conf_correct for s in results.field_stats.values())
    total_med = sum(s.medium_conf_total for s in results.field_stats.values())
    correct_med = sum(s.medium_conf_correct for s in results.field_stats.values())
    total_low = sum(s.low_conf_total for s in results.field_stats.values())
    correct_low = sum(s.low_conf_correct for s in results.field_stats.values())
    
    if total_high > 0:
        print(f"High confidence:   {correct_high}/{total_high} correct ({correct_high/total_high:.1%})")
    if total_med > 0:
        print(f"Medium confidence: {correct_med}/{total_med} correct ({correct_med/total_med:.1%})")
    if total_low > 0:
        print(f"Low confidence:    {correct_low}/{total_low} correct ({correct_low/total_low:.1%})")
    
    # Show worst performing fields
    print("\n" + "-" * 80)
    print("FIELDS NEEDING ATTENTION (accuracy < 90%)")
    print("-" * 80)
    
    problem_fields = [
        (name, stats) for name, stats in results.field_stats.items()
        if stats.total > 0 and stats.accuracy < 0.9
    ]
    problem_fields.sort(key=lambda x: x[1].accuracy)
    
    if problem_fields:
        for name, stats in problem_fields:
            print(f"  {name}: {stats.accuracy:.1%} accuracy ({stats.false_negatives} missed, {stats.false_positives} hallucinated)")
    else:
        print("  All fields performing above 90% accuracy!")
    
    print("\n" + "=" * 80)


def generate_template(image_paths: list[str], output_path: str) -> None:
    """Generate a ground truth template with empty expected values."""
    labels = []
    
    for i, path in enumerate(image_paths):
        # Guess beverage type from path
        path_lower = path.lower()
        if "spirit" in path_lower or "whiskey" in path_lower or "vodka" in path_lower:
            beverage_type = "spirits"
        elif "wine" in path_lower:
            beverage_type = "wine"
        elif "beer" in path_lower:
            beverage_type = "beer"
        else:
            beverage_type = "spirits"  # default
        
        # Guess panel type
        if "back" in path_lower:
            panel_type = "back"
        elif "other" in path_lower or "side" in path_lower or "neck" in path_lower:
            panel_type = "other"
        else:
            panel_type = "front"
        
        labels.append({
            "id": f"label-{i+1:03d}",
            "image_path": path,
            "panel_type": panel_type,
            "beverage_type": beverage_type,
            "expected_fields": {f: None for f in EVAL_FIELDS},
            "notes": "TODO: Fill in expected values from visual inspection"
        })
    
    output = {
        "version": "1.0",
        "labels": labels,
    }
    
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"Generated template with {len(labels)} entries: {output_path}")
    print("Edit the file to fill in expected_fields values.")


async def main():
    parser = argparse.ArgumentParser(description="Evaluate LabelVerifier extraction accuracy")
    parser.add_argument(
        "--ground-truth", "-g",
        default="evals/ground_truth_data.json",
        help="Path to ground truth JSON file"
    )
    parser.add_argument(
        "--output", "-o",
        help="Save detailed results to JSON file"
    )
    parser.add_argument(
        "--generate-template",
        metavar="GLOB",
        help="Generate template from image glob pattern (e.g., 'test data/**/*.jpg')"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "groq"],
        default=settings.llm_provider,
        help="LLM provider to use"
    )
    
    args = parser.parse_args()
    
    # Handle template generation
    if args.generate_template:
        image_paths = glob.glob(args.generate_template, recursive=True)
        if not image_paths:
            print(f"No images found matching: {args.generate_template}")
            sys.exit(1)
        generate_template(image_paths, "evals/ground_truth_template.json")
        return
    
    # Load ground truth
    base_path = Path(__file__).parent.parent
    gt_path = base_path / args.ground_truth
    
    if not gt_path.exists():
        print(f"Ground truth file not found: {gt_path}")
        print("Run with --generate-template to create one.")
        sys.exit(1)
    
    with open(gt_path) as f:
        ground_truth = json.load(f)
    
    labels = ground_truth.get("labels", [])
    if not labels:
        print("No labels found in ground truth file.")
        sys.exit(1)
    
    # Create extractor
    if args.provider == "anthropic":
        extractor = AnthropicExtractor(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )
    else:
        extractor = GroqExtractor(
            api_key=settings.groq_api_key,
            model=settings.llm_model,
        )
    
    print(f"Evaluating {len(labels)} labels with {args.provider}...")
    
    # Run evaluation
    results = EvalResults(total_labels=len(labels))
    
    for label in labels:
        print(f"  Processing: {label['id']}...", end=" ", flush=True)
        label_result = await evaluate_label(extractor, label, base_path)
        results.label_results.append(label_result)
        
        if label_result.extraction_error:
            print(f"ERROR: {label_result.extraction_error[:50]}")
        else:
            correct = sum(1 for fr in label_result.field_results if fr.correct)
            print(f"{correct}/{len(EVAL_FIELDS)} fields correct")
    
    # Aggregate and print results
    aggregate_stats(results)
    print_results(results)
    
    # Save detailed results if requested
    if args.output:
        output_data = {
            "total_labels": results.total_labels,
            "successful_extractions": results.successful_extractions,
            "failed_extractions": results.failed_extractions,
            "field_stats": {
                name: {
                    "accuracy": stats.accuracy,
                    "precision": stats.precision,
                    "recall": stats.recall,
                    "f1": stats.f1,
                    "high_conf_accuracy": stats.high_conf_accuracy,
                    "total": stats.total,
                    "correct": stats.correct,
                    "true_positives": stats.true_positives,
                    "false_positives": stats.false_positives,
                    "false_negatives": stats.false_negatives,
                }
                for name, stats in results.field_stats.items()
            },
            "label_results": [
                {
                    "label_id": lr.label_id,
                    "image_path": lr.image_path,
                    "extraction_error": lr.extraction_error,
                    "fields": {
                        fr.field_name: {
                            "expected": fr.expected,
                            "extracted": fr.extracted,
                            "correct": fr.correct,
                            "similarity": fr.similarity,
                            "confidence": fr.confidence,
                        }
                        for fr in lr.field_results
                    }
                }
                for lr in results.label_results
            ]
        }
        
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nDetailed results saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
