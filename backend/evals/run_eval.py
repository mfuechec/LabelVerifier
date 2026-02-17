#!/usr/bin/env python3
"""
End-to-end pipeline evaluation for LabelVerifier.

Calls VerificationOrchestrator.verify_single() per product and compares
the full pipeline output (status, per-field comparison results, confidence,
cost) against ground truth expectations.

Usage:
    cd backend
    python -m evals.run_eval
    python -m evals.run_eval --max-products 2
    python -m evals.run_eval --filter "angels-envy"
    python -m evals.run_eval --output results.json
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.models.schemas import ApplicationData, VerificationResult


# ---------------------------------------------------------------------------
# Pure helpers (kept from v1)
# ---------------------------------------------------------------------------

def normalize_for_comparison(text: str | None) -> str:
    """Normalize text for fuzzy comparison."""
    if text is None:
        return ""
    text = re.sub(r'\s+', ' ', text.strip().lower())
    return text


def compare_field(expected: str | None, extracted: str | None, threshold: int = 85) -> tuple[bool, float]:
    """Compare expected vs extracted value. Returns (is_correct, similarity)."""
    if expected is None and extracted is None:
        return True, 100.0
    if expected is None or extracted is None:
        return False, 0.0
    norm_exp = normalize_for_comparison(expected)
    norm_ext = normalize_for_comparison(extracted)
    similarity = max(
        fuzz.ratio(norm_ext, norm_exp),
        fuzz.token_sort_ratio(norm_ext, norm_exp),
        fuzz.token_set_ratio(norm_ext, norm_exp),
    )
    return similarity >= threshold, similarity


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FieldAssertion:
    """Expected vs actual status for a single field."""
    field_name: str
    expected_status: str   # from ground truth: match, content_mismatch, field_missing, extraction_uncertain
    actual_status: str | None  # from pipeline VerificationResult field
    correct: bool          # expected_status == actual_status
    declared_value: str | None = None
    extracted_value: str | None = None


@dataclass
class ProductResult:
    """Pipeline result for a single product vs ground truth."""
    product_id: str
    expected_status: str
    actual_status: str
    status_correct: bool
    field_assertions: list[FieldAssertion]
    overall_confidence: float = 0.0
    total_time_ms: int = 0
    llm_calls: int = 0
    cost_usd: float = 0.0
    error: str | None = None


@dataclass
class EvalSummary:
    """Aggregated metrics across all products."""
    total_products: int = 0
    products_evaluated: int = 0
    products_errored: int = 0
    # Status accuracy
    status_correct: int = 0
    status_confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    # Field assertion accuracy
    field_assertions_total: int = 0
    field_assertions_correct: int = 0
    field_accuracy_by_name: dict[str, dict[str, int]] = field(default_factory=dict)
    # Cost/performance
    total_cost_usd: float = 0.0
    total_time_ms: int = 0
    total_llm_calls: int = 0
    product_results: list[ProductResult] = field(default_factory=list)

    @property
    def status_accuracy(self) -> float:
        return self.status_correct / self.products_evaluated if self.products_evaluated > 0 else 0.0

    @property
    def field_accuracy(self) -> float:
        return self.field_assertions_correct / self.field_assertions_total if self.field_assertions_total > 0 else 0.0

    @property
    def avg_cost_per_product(self) -> float:
        return self.total_cost_usd / self.products_evaluated if self.products_evaluated > 0 else 0.0

    @property
    def avg_time_per_product_ms(self) -> float:
        return self.total_time_ms / self.products_evaluated if self.products_evaluated > 0 else 0.0


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

def build_field_assertions(
    expected_fields: dict[str, str],
    result: VerificationResult,
) -> list[FieldAssertion]:
    """Compare expected field statuses against pipeline output."""
    # Index pipeline fields by name
    actual_by_name: dict[str, Any] = {}
    for f in result.fields:
        actual_by_name[f.field_name] = f

    assertions = []
    for field_name, expected_status in expected_fields.items():
        actual_field = actual_by_name.get(field_name)
        if actual_field is None:
            # Pipeline didn't produce a result for this field
            actual_status = None
            correct = False
            declared = None
            extracted = None
        else:
            actual_status = actual_field.status
            correct = expected_status == actual_status
            declared = actual_field.declared_value
            extracted = actual_field.extracted_value

        assertions.append(FieldAssertion(
            field_name=field_name,
            expected_status=expected_status,
            actual_status=actual_status,
            correct=correct,
            declared_value=declared,
            extracted_value=extracted,
        ))

    return assertions


def aggregate_summary(product_results: list[ProductResult]) -> EvalSummary:
    """Aggregate metrics from product results into a summary."""
    summary = EvalSummary(
        total_products=len(product_results),
        product_results=product_results,
    )

    for pr in product_results:
        if pr.error:
            summary.products_errored += 1
            continue

        summary.products_evaluated += 1
        if pr.status_correct:
            summary.status_correct += 1

        # Status confusion matrix
        key = f"{pr.expected_status}->{pr.actual_status}"
        if pr.expected_status not in summary.status_confusion:
            summary.status_confusion[pr.expected_status] = {}
        actual_map = summary.status_confusion[pr.expected_status]
        actual_map[pr.actual_status] = actual_map.get(pr.actual_status, 0) + 1

        # Field assertions
        for fa in pr.field_assertions:
            summary.field_assertions_total += 1
            if fa.correct:
                summary.field_assertions_correct += 1

            if fa.field_name not in summary.field_accuracy_by_name:
                summary.field_accuracy_by_name[fa.field_name] = {"total": 0, "correct": 0}
            summary.field_accuracy_by_name[fa.field_name]["total"] += 1
            if fa.correct:
                summary.field_accuracy_by_name[fa.field_name]["correct"] += 1

        # Cost/perf
        summary.total_cost_usd += pr.cost_usd
        summary.total_time_ms += pr.total_time_ms
        summary.total_llm_calls += pr.llm_calls

    return summary


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

async def evaluate_product(
    product: dict,
    test_data_root: Path,
    db_path: str,
    images_base_dir: str,
) -> ProductResult:
    """Run the pipeline on a single product and build assertions."""
    import app.services.orchestrator as orch_module
    from app.db.setup import get_db, create_tables
    from app.services.orchestrator import VerificationOrchestrator

    product_id = product["id"]
    source_folder = product["source_folder"]
    image_files = product["image_files"]
    panels = product["panels"]
    app_data_raw = product["application_data"]
    expected_status = product["expected_status"]
    expected_fields = product["expected_fields"]

    # Load images from test data
    images: list[bytes] = []
    for img_file in image_files:
        img_path = test_data_root / source_folder / img_file
        if not img_path.exists():
            return ProductResult(
                product_id=product_id,
                expected_status=expected_status,
                actual_status="error",
                status_correct=False,
                field_assertions=[],
                error=f"Image not found: {img_path}",
            )
        images.append(img_path.read_bytes())

    # Build ApplicationData (fill required fields with defaults if missing)
    app_data_dict = {
        "brand_name": app_data_raw.get("brand_name", "UNKNOWN"),
        "class_type": app_data_raw.get("class_type", "UNKNOWN"),
        "alcohol_content": app_data_raw.get("alcohol_content", "0%"),
        "net_contents": app_data_raw.get("net_contents", "0 mL"),
        "beverage_type": app_data_raw.get("beverage_type", "distilled_spirits"),
    }
    # Copy optional fields
    for opt_field in [
        "producer_name", "producer_address", "country_of_origin",
        "importer_name", "importer_address", "fanciful_name",
        "source_of_product", "has_sulfites_declaration",
    ]:
        if opt_field in app_data_raw:
            app_data_dict[opt_field] = app_data_raw[opt_field]

    app_data = ApplicationData(**app_data_dict)

    # Patch IMAGES_BASE_DIR for this run
    original_images_dir = orch_module.IMAGES_BASE_DIR
    orch_module.IMAGES_BASE_DIR = images_base_dir

    try:
        orchestrator = VerificationOrchestrator(db_path=db_path)
        result = await orchestrator.verify_single(images, panels, app_data)
    except Exception as e:
        return ProductResult(
            product_id=product_id,
            expected_status=expected_status,
            actual_status="error",
            status_correct=False,
            field_assertions=[],
            error=str(e),
        )
    finally:
        orch_module.IMAGES_BASE_DIR = original_images_dir

    # Build assertions
    field_assertions = build_field_assertions(expected_fields, result)
    status_correct = expected_status == result.status

    stats = result.processing_stats
    return ProductResult(
        product_id=product_id,
        expected_status=expected_status,
        actual_status=result.status,
        status_correct=status_correct,
        field_assertions=field_assertions,
        overall_confidence=result.overall_confidence,
        total_time_ms=stats.total_time_ms if stats else 0,
        llm_calls=stats.total_llm_calls if stats else 0,
        cost_usd=stats.estimated_cost_usd if stats else 0.0,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(summary: EvalSummary) -> None:
    """Print the evaluation report to stdout."""
    print("\n" + "=" * 80)
    print("LABELVERIFIER END-TO-END PIPELINE EVALUATION")
    print("=" * 80)

    print(f"\nProducts: {summary.products_evaluated} evaluated, {summary.products_errored} errored, {summary.total_products} total")
    print(f"Status accuracy: {summary.status_correct}/{summary.products_evaluated} ({summary.status_accuracy:.1%})")
    print(f"Field assertion accuracy: {summary.field_assertions_correct}/{summary.field_assertions_total} ({summary.field_accuracy:.1%})")

    # Status confusion matrix
    print("\n" + "-" * 80)
    print("STATUS CONFUSION MATRIX (expected -> actual)")
    print("-" * 80)
    for expected, actuals in sorted(summary.status_confusion.items()):
        parts = [f"{actual}={count}" for actual, count in sorted(actuals.items())]
        print(f"  {expected}: {', '.join(parts)}")

    # Per-field accuracy
    print("\n" + "-" * 80)
    print(f"{'Field':<30} | {'Accuracy':>8} | {'Correct':>7} | {'Total':>5}")
    print("-" * 80)
    for field_name, counts in sorted(summary.field_accuracy_by_name.items()):
        total = counts["total"]
        correct = counts["correct"]
        acc = correct / total if total > 0 else 0.0
        print(f"  {field_name:<28} | {acc:>7.1%} | {correct:>7} | {total:>5}")

    # Cost/performance
    print("\n" + "-" * 80)
    print("COST & PERFORMANCE")
    print("-" * 80)
    print(f"  Total cost:          ${summary.total_cost_usd:.4f}")
    print(f"  Avg cost/product:    ${summary.avg_cost_per_product:.4f}")
    print(f"  Total time:          {summary.total_time_ms / 1000:.1f}s")
    print(f"  Avg time/product:    {summary.avg_time_per_product_ms / 1000:.1f}s")
    print(f"  Total LLM calls:     {summary.total_llm_calls}")
    if summary.products_evaluated > 0:
        print(f"  Avg LLM calls/prod:  {summary.total_llm_calls / summary.products_evaluated:.1f}")

    # Per-product details
    print("\n" + "-" * 80)
    print("PER-PRODUCT RESULTS")
    print("-" * 80)
    for pr in summary.product_results:
        if pr.error:
            print(f"  {pr.product_id}: ERROR - {pr.error[:60]}")
            continue
        status_mark = "OK" if pr.status_correct else "WRONG"
        field_correct = sum(1 for fa in pr.field_assertions if fa.correct)
        field_total = len(pr.field_assertions)
        print(
            f"  {pr.product_id:<30} "
            f"status={pr.actual_status:<12} [{status_mark}] "
            f"fields={field_correct}/{field_total} "
            f"${pr.cost_usd:.4f} {pr.total_time_ms / 1000:.1f}s"
        )
        # Show wrong field assertions
        for fa in pr.field_assertions:
            if not fa.correct:
                print(
                    f"    ! {fa.field_name}: expected={fa.expected_status} "
                    f"actual={fa.actual_status}"
                )

    print("\n" + "=" * 80)


def save_results(summary: EvalSummary, output_path: str) -> None:
    """Save detailed JSON results."""
    data = {
        "total_products": summary.total_products,
        "products_evaluated": summary.products_evaluated,
        "products_errored": summary.products_errored,
        "status_accuracy": summary.status_accuracy,
        "field_accuracy": summary.field_accuracy,
        "total_cost_usd": summary.total_cost_usd,
        "total_time_ms": summary.total_time_ms,
        "total_llm_calls": summary.total_llm_calls,
        "status_confusion": summary.status_confusion,
        "field_accuracy_by_name": summary.field_accuracy_by_name,
        "product_results": [
            {
                "product_id": pr.product_id,
                "expected_status": pr.expected_status,
                "actual_status": pr.actual_status,
                "status_correct": pr.status_correct,
                "overall_confidence": pr.overall_confidence,
                "cost_usd": pr.cost_usd,
                "total_time_ms": pr.total_time_ms,
                "llm_calls": pr.llm_calls,
                "error": pr.error,
                "field_assertions": [
                    {
                        "field_name": fa.field_name,
                        "expected_status": fa.expected_status,
                        "actual_status": fa.actual_status,
                        "correct": fa.correct,
                        "declared_value": fa.declared_value,
                        "extracted_value": fa.extracted_value,
                    }
                    for fa in pr.field_assertions
                ],
            }
            for pr in summary.product_results
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nDetailed results saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="End-to-end pipeline evaluation")
    parser.add_argument(
        "--ground-truth", "-g",
        default="evals/eval_ground_truth.json",
        help="Path to eval ground truth JSON (default: evals/eval_ground_truth.json)",
    )
    parser.add_argument("--output", "-o", help="Save detailed JSON results to file")
    parser.add_argument("--concurrency", "-c", type=int, default=3, help="Max parallel products (default: 3)")
    parser.add_argument("--max-products", "-n", type=int, help="Limit number of products (for quick tests)")
    parser.add_argument("--filter", "-f", help="Filter by product ID or source_folder (substring match)")
    args = parser.parse_args()

    # Load ground truth
    base_path = Path(__file__).parent.parent
    gt_path = base_path / args.ground_truth
    if not gt_path.exists():
        print(f"Ground truth not found: {gt_path}")
        print("Run: python -m evals.convert_catalog")
        sys.exit(1)

    with open(gt_path) as f:
        ground_truth = json.load(f)

    products = ground_truth.get("products", [])
    if not products:
        print("No products in ground truth.")
        sys.exit(1)

    # Apply filter
    if args.filter:
        filt = args.filter.lower()
        products = [
            p for p in products
            if filt in p["id"].lower() or filt in p.get("source_folder", "").lower()
        ]
        if not products:
            print(f"No products match filter: {args.filter}")
            sys.exit(1)

    # Apply limit
    if args.max_products:
        products = products[:args.max_products]

    # Test data root
    test_data_root = base_path.parent / "test data"
    if not test_data_root.exists():
        print(f"Test data directory not found: {test_data_root}")
        sys.exit(1)

    # Create temp dirs for DB and images
    tmp_dir = tempfile.mkdtemp(prefix="eval_")
    db_path = os.path.join(tmp_dir, "eval.db")
    images_dir = os.path.join(tmp_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Initialize temp DB
    from app.db.setup import get_db, create_tables
    conn = get_db(db_path)
    create_tables(conn)
    conn.close()

    print(f"Evaluating {len(products)} products (concurrency={args.concurrency})...")
    print(f"Temp dir: {tmp_dir}")

    # Run evaluations with bounded concurrency
    semaphore = asyncio.Semaphore(args.concurrency)

    async def eval_with_semaphore(product: dict) -> ProductResult:
        async with semaphore:
            return await evaluate_product(product, test_data_root, db_path, images_dir)

    t_start = time.monotonic()
    results = await asyncio.gather(
        *(eval_with_semaphore(p) for p in products)
    )
    wall_time = time.monotonic() - t_start

    # Progress output
    for pr in results:
        if pr.error:
            print(f"  {pr.product_id}: ERROR: {pr.error[:60]}")
        else:
            fc = sum(1 for fa in pr.field_assertions if fa.correct)
            ft = len(pr.field_assertions)
            mark = "OK" if pr.status_correct else "WRONG"
            print(f"  {pr.product_id}: status={pr.actual_status} [{mark}], fields={fc}/{ft}")

    # Aggregate and report
    summary = aggregate_summary(list(results))
    print_report(summary)
    print(f"Wall clock time: {wall_time:.1f}s")

    if args.output:
        save_results(summary, args.output)

    # Cleanup temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
