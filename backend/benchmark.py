#!/usr/bin/env python3
"""LabelVerify accuracy benchmark -- runs real LLM extraction + comparison
against all test fixtures and produces an accuracy report.

Usage:
    python benchmark.py                              # run all 46 fixtures (sync)
    python benchmark.py --fixture fixture-1-angels-envy
    python benchmark.py --category "good spirits"
    python benchmark.py --save                       # save JSON results file
    python benchmark.py --quick                      # run ~10 representative fixtures
    python benchmark.py --no-cache                   # disable extraction cache
    python benchmark.py --clear-cache                # wipe cache before running
    python benchmark.py --batch                      # submit + poll + score via Groq Batch API
    python benchmark.py --batch --submit-only        # just submit, print batch_id
    python benchmark.py --batch --results BATCH_ID   # retrieve + score a previous batch

Requires GROQ_API_KEY env var (real API calls).
"""

import argparse
import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone

# Add backend to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import Settings
from app.models.schemas import ApplicationData
from app.services.extraction import ExtractionService, ExtractionResult, EXTRACTION_PROMPT, _repair_json
from app.services.comparison import ComparisonService, ConfidenceScorer
from app.services.merger import ImageMerger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tests", "fixtures", "sample_applications.json",
)
TEST_DATA_ROOT = os.path.join(PROJECT_ROOT, "test data")

CATEGORY_TO_FOLDER = {
    "good spirits": "good spirits",
    "good wine+beer": "good wine+beer",
    "bad spirits label": "bad spirits label",
    "bad spirits photo": "bad spirits photo",
    "bad spirits warning": "bad spirits warning",
    "bad wine+beer": "bad wine+beer",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".benchmark_cache")


# ---------------------------------------------------------------------------
# Disk-based extraction cache
# ---------------------------------------------------------------------------


class BenchmarkCache:
    """Caches LLM extraction results on disk, keyed on SHA256(image_bytes + prompt)."""

    def __init__(self, cache_dir: str = CACHE_DIR, enabled: bool = True):
        self._cache_dir = cache_dir
        self._enabled = enabled
        self._hits = 0
        self._misses = 0
        if enabled:
            os.makedirs(cache_dir, exist_ok=True)

    def _cache_key(self, image_bytes: bytes, prompt: str) -> str:
        h = hashlib.sha256()
        h.update(image_bytes)
        h.update(prompt.encode("utf-8"))
        return h.hexdigest()

    def get(self, image_bytes: bytes, prompt: str) -> "ExtractionResult | None":
        if not self._enabled:
            return None
        key = self._cache_key(image_bytes, prompt)
        path = os.path.join(self._cache_dir, f"{key}.json")
        if not os.path.exists(path):
            self._misses += 1
            return None
        with open(path) as f:
            data = json.load(f)
        self._hits += 1
        return ExtractionResult(**data)

    def put(self, image_bytes: bytes, prompt: str, result: "ExtractionResult"):
        if not self._enabled:
            return
        key = self._cache_key(image_bytes, prompt)
        path = os.path.join(self._cache_dir, f"{key}.json")
        with open(path, "w") as f:
            json.dump(asdict(result), f)

    def clear(self):
        if os.path.exists(self._cache_dir):
            shutil.rmtree(self._cache_dir)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def stats(self) -> str:
        if not self._enabled:
            return "Cache: disabled"
        total = self._hits + self._misses
        pct = (100 * self._hits // total) if total > 0 else 0
        return f"Cache: {self._hits} hits, {self._misses} misses ({pct}% hit rate)"


# ---------------------------------------------------------------------------
# Adaptive request throttling
# ---------------------------------------------------------------------------


class RateThrottle:
    """Proactive delay between API calls to avoid 429 storms."""

    def __init__(self, initial_delay: float = 3.0, min_delay: float = 1.0, max_delay: float = 10.0):
        self._delay = initial_delay
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._last_request = 0.0
        self._successes = 0
        self._rate_limits = 0

    async def wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self._delay:
            await asyncio.sleep(self._delay - elapsed)
        self._last_request = time.time()

    def on_success(self):
        self._successes += 1
        self._delay = max(self._min_delay, self._delay * 0.9)

    def on_rate_limit(self):
        self._rate_limits += 1
        self._delay = min(self._max_delay, self._delay * 1.5)

    def stats(self) -> str:
        return (
            f"Throttle: {self._successes} success, {self._rate_limits} rate_limit, "
            f"current_delay={self._delay:.1f}s"
        )


# ---------------------------------------------------------------------------
# Quick subset selection
# ---------------------------------------------------------------------------


def select_quick_subset(fixtures: list[dict]) -> list[dict]:
    """Select a representative subset: 2 per category (1 for small categories)."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for fx in fixtures:
        by_cat[fx["category"]].append(fx)
    subset = []
    for cat in sorted(by_cat.keys()):
        n = 1 if len(by_cat[cat]) <= 3 else 2
        subset.extend(by_cat[cat][:n])
    return subset


def load_fixtures(fixture_id: str | None = None, category: str | None = None) -> list[dict]:
    with open(FIXTURES_PATH) as f:
        data = json.load(f)

    fixtures = data["fixtures"]

    if fixture_id:
        fixtures = [fx for fx in fixtures if fx["id"] == fixture_id]
        if not fixtures:
            print(f"ERROR: Fixture '{fixture_id}' not found.")
            sys.exit(1)

    if category:
        fixtures = [fx for fx in fixtures if fx["category"] == category]
        if not fixtures:
            print(f"ERROR: No fixtures in category '{category}'.")
            sys.exit(1)

    return fixtures


def load_images(fixture: dict) -> tuple[list[bytes], list[str]]:
    """Load image files for a fixture. Returns (image_bytes_list, panels_list)."""
    category = fixture["category"]
    folder = os.path.join(TEST_DATA_ROOT, CATEGORY_TO_FOLDER[category])

    image_bytes = []
    panels = []
    for img_info in fixture["images"]:
        img_path = os.path.join(folder, img_info["filename"])
        if not os.path.exists(img_path):
            print(f"  WARNING: Image not found: {img_path}")
            continue
        with open(img_path, "rb") as f:
            image_bytes.append(f.read())
        panels.append(img_info["panel"])

    return image_bytes, panels


def load_image_paths(fixture: dict) -> tuple[list[str], list[str]]:
    """Load image file paths for a fixture. Returns (paths_list, panels_list)."""
    category = fixture["category"]
    folder = os.path.join(TEST_DATA_ROOT, CATEGORY_TO_FOLDER[category])

    paths = []
    panels = []
    for img_info in fixture["images"]:
        img_path = os.path.join(folder, img_info["filename"])
        if not os.path.exists(img_path):
            print(f"  WARNING: Image not found: {img_path}")
            continue
        paths.append(img_path)
        panels.append(img_info["panel"])

    return paths, panels


async def run_single_fixture(
    fixture: dict,
    extraction_service: ExtractionService,
    comparison_service: ComparisonService,
    merger: ImageMerger,
    scorer: ConfidenceScorer,
    cache: BenchmarkCache | None = None,
    throttle: RateThrottle | None = None,
) -> dict:
    """Run extraction + comparison on a single fixture. Returns result dict."""
    fixture_id = fixture["id"]
    app_data_raw = fixture["application_data"]
    expected = fixture["expected_outcome"]

    # Build ApplicationData
    app_data = ApplicationData(**app_data_raw)

    # Load images
    image_bytes, panels = load_images(fixture)
    if not image_bytes:
        return {
            "fixture_id": fixture_id,
            "category": fixture["category"],
            "error": "No images found",
            "expected_status": expected["overall_status"],
            "actual_status": None,
            "correct": False,
            "field_results": {},
        }

    # Extract fields from each panel
    extraction_results = []
    for img, panel in zip(image_bytes, panels):
        # Check cache first
        if cache is not None:
            cached = cache.get(img, EXTRACTION_PROMPT)
            if cached is not None:
                extraction_results.append(cached)
                continue

        try:
            if throttle is not None:
                await throttle.wait()
            t0 = time.time()
            result = await extraction_service.extract_fields(img, panel)
            elapsed = time.time() - t0
            if throttle is not None:
                if elapsed > 10.0:
                    throttle.on_rate_limit()
                else:
                    throttle.on_success()
            if cache is not None:
                cache.put(img, EXTRACTION_PROMPT, result)
            extraction_results.append(result)
        except Exception as e:
            print(f"  Extraction error on {panel}: {e}")
            extraction_results.append(ExtractionResult(panel_type=panel, error=str(e)))

    return score_fixture(fixture, extraction_results, comparison_service, merger, scorer)


def score_fixture(
    fixture: dict,
    extraction_results: list[ExtractionResult],
    comparison_service: ComparisonService,
    merger: ImageMerger,
    scorer: ConfidenceScorer,
) -> dict:
    """Score extraction results against fixture expectations. Shared by sync and batch modes."""
    fixture_id = fixture["id"]
    app_data_raw = fixture["application_data"]
    expected = fixture["expected_outcome"]
    app_data = ApplicationData(**app_data_raw)

    # Merge panels
    extraction_confidences = {}
    if len(extraction_results) == 1:
        merged_fields = {}
        result = extraction_results[0]
        for field_name, field_data in result.fields.items():
            if isinstance(field_data, dict):
                merged_fields[field_name] = field_data.get("value")
                extraction_confidences[field_name] = field_data.get("extraction_confidence", "high")
    elif len(extraction_results) > 1:
        panel_data = {}
        for result in extraction_results:
            panel_fields = {}
            for field_name, field_data in result.fields.items():
                if isinstance(field_data, dict):
                    panel_fields[field_name] = {
                        "value": field_data.get("value"),
                        "confidence": 90.0,
                        "bounding_box": field_data.get("bounding_box"),
                        "extraction_confidence": field_data.get("extraction_confidence", "high"),
                    }
            panel_data[result.panel_type] = panel_fields

        merged = merger.merge_panels(panel_data)
        merged_fields = {fn: fv.value for fn, fv in merged.fields.items()}
        extraction_confidences = {fn: fv.extraction_confidence for fn, fv in merged.fields.items()}
    else:
        merged_fields = {}

    # Compare
    comparison_results = comparison_service.compare_fields(
        merged_fields, app_data, app_data.beverage_type,
        extraction_confidences=extraction_confidences,
    )

    # Score
    overall_confidence, actual_status = scorer.calculate(comparison_results)

    # Check extraction errors
    has_error = any(r.error for r in extraction_results)
    if has_error and not merged_fields:
        actual_status = "needs_review"
        overall_confidence = 0.0

    # Build field-level results
    field_results = {}
    expected_fields = expected.get("expected_field_results", expected.get("field_expectations", {}))
    for cr in comparison_results:
        expected_field_status = expected_fields.get(cr.field_name)
        field_results[cr.field_name] = {
            "actual_status": cr.status,
            "expected_status": expected_field_status,
            "correct": expected_field_status is None or cr.status == expected_field_status,
            "confidence": cr.confidence,
            "declared": cr.declared_value,
            "extracted": cr.extracted_value,
        }

    expected_status = expected["overall_status"]
    correct = actual_status == expected_status

    return {
        "fixture_id": fixture_id,
        "category": fixture["category"],
        "expected_status": expected_status,
        "actual_status": actual_status,
        "overall_confidence": overall_confidence,
        "correct": correct,
        "field_results": field_results,
    }


def print_report(results: list[dict], model_name: str, elapsed: float):
    total = len(results)
    correct = sum(1 for r in results if r["correct"])

    print()
    print("=" * 60)
    print("=== LabelVerify Accuracy Benchmark ===")
    print(f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Model: {model_name}")
    print(f"Time: {elapsed:.1f}s ({elapsed/total:.1f}s per fixture)")
    print()
    print(f"OVERALL: {correct}/{total} correct ({100*correct/total:.1f}%)")

    # By category
    categories = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        cat = r["category"]
        categories[cat]["total"] += 1
        if r["correct"]:
            categories[cat]["correct"] += 1

    print()
    print("BY CATEGORY:")
    for cat in sorted(categories.keys()):
        s = categories[cat]
        pct = 100 * s["correct"] / s["total"] if s["total"] else 0
        print(f"  {cat:25s} {s['correct']:>2}/{s['total']:<2}  ({pct:.1f}%)")

    # Field-level accuracy
    field_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        for fname, fdata in r["field_results"].items():
            if fdata["expected_status"] is not None:
                field_stats[fname]["total"] += 1
                if fdata["correct"]:
                    field_stats[fname]["correct"] += 1

    if field_stats:
        print()
        print("FIELD-LEVEL ACCURACY:")
        for fname in sorted(field_stats.keys()):
            s = field_stats[fname]
            pct = 100 * s["correct"] / s["total"] if s["total"] else 0
            print(f"  {fname:25s} {s['correct']:>2}/{s['total']:<2}  ({pct:.1f}%)")

    # Failures
    failures = [r for r in results if not r["correct"]]
    if failures:
        print()
        print(f"FAILURES ({len(failures)}):")
        for r in failures:
            print(f"  {r['fixture_id']}: expected {r['expected_status']}, got {r['actual_status']}")
            for fname, fdata in r["field_results"].items():
                if fdata["expected_status"] and not fdata["correct"]:
                    print(f"    - {fname}: expected {fdata['expected_status']}, got {fdata['actual_status']}")

    print()
    print("=" * 60)


# ---------------------------------------------------------------------------
# Batch mode (Groq Batch API)
# ---------------------------------------------------------------------------


def _build_batch_request(custom_id: str, image_path: str, model: str) -> dict:
    """Build a single batch API request line for a fixture+panel image."""
    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    image_url = f"data:{mime_type};base64,{b64}"

    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_tokens": 2048,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
        },
    }


def generate_batch_jsonl(fixtures: list[dict], model: str) -> tuple[str, dict]:
    """Generate JSONL file for Groq Batch API.

    Returns (jsonl_path, custom_id_map) where custom_id_map maps
    custom_id -> {"fixture_idx": int, "panel": str} for result mapping.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"benchmark_batch_{ts}.jsonl",
    )
    custom_id_map = {}
    line_count = 0

    with open(jsonl_path, "w") as f:
        for fx_idx, fixture in enumerate(fixtures):
            fixture_id = fixture["id"]
            paths, panels = load_image_paths(fixture)

            for img_path, panel in zip(paths, panels):
                custom_id = f"{fixture_id}__{panel}"
                request = _build_batch_request(custom_id, img_path, model)
                f.write(json.dumps(request) + "\n")
                custom_id_map[custom_id] = {
                    "fixture_idx": fx_idx,
                    "panel": panel,
                }
                line_count += 1

    print(f"Generated {line_count} batch requests in: {jsonl_path}")
    return jsonl_path, custom_id_map


def submit_batch(api_key: str, jsonl_path: str) -> str:
    """Upload JSONL and create a Groq batch. Returns batch_id."""
    from groq import Groq

    client = Groq(api_key=api_key)

    print("Uploading JSONL file...")
    with open(jsonl_path, "rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")
    print(f"  File uploaded: {file_obj.id}")

    print("Creating batch...")
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"  Batch created: {batch.id}")
    print(f"  Status: {batch.status}")

    return batch.id


def poll_batch(api_key: str, batch_id: str, poll_interval: int = 30) -> object:
    """Poll batch until completion. Returns the batch object."""
    from groq import Groq

    client = Groq(api_key=api_key)
    print(f"Polling batch {batch_id} every {poll_interval}s...")

    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status
        completed = getattr(batch.request_counts, "completed", 0) if batch.request_counts else 0
        total = getattr(batch.request_counts, "total", 0) if batch.request_counts else 0
        failed = getattr(batch.request_counts, "failed", 0) if batch.request_counts else 0

        ts_now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"  [{ts_now}] status={status}  completed={completed}/{total}  failed={failed}")

        if status in ("completed", "failed", "expired", "cancelled"):
            return batch

        time.sleep(poll_interval)


def download_batch_results(api_key: str, batch: object) -> list[dict]:
    """Download and parse batch output. Returns list of result dicts."""
    from groq import Groq

    client = Groq(api_key=api_key)

    if batch.status != "completed":
        print(f"Batch status is '{batch.status}', not 'completed'.")
        if hasattr(batch, "errors") and batch.errors:
            print(f"  Errors: {batch.errors}")
        return []

    output_file_id = batch.output_file_id
    if not output_file_id:
        print("No output file available.")
        return []

    print(f"Downloading results from file {output_file_id}...")
    content = client.files.content(output_file_id)
    # content is a binary response; decode to text
    text = content.text if hasattr(content, "text") else content.read().decode("utf-8")

    results = []
    for line in text.strip().split("\n"):
        if line.strip():
            results.append(json.loads(line))

    print(f"  Downloaded {len(results)} results.")
    return results


def batch_results_to_extraction(
    batch_results: list[dict],
    custom_id_map: dict,
    fixtures: list[dict],
) -> dict[int, list[ExtractionResult]]:
    """Convert batch API results to ExtractionResult objects grouped by fixture index."""
    # Group by fixture index
    grouped: dict[int, list[tuple[str, ExtractionResult]]] = defaultdict(list)

    for result in batch_results:
        custom_id = result.get("custom_id", "")
        mapping = custom_id_map.get(custom_id)
        if not mapping:
            print(f"  WARNING: Unknown custom_id: {custom_id}")
            continue

        fx_idx = mapping["fixture_idx"]
        panel = mapping["panel"]

        # Extract the LLM response text
        error = result.get("error")
        if error:
            grouped[fx_idx].append((panel, ExtractionResult(
                panel_type=panel, error=f"Batch error: {error}"
            )))
            continue

        response_body = result.get("response", {}).get("body", {})
        choices = response_body.get("choices", [])
        if not choices:
            grouped[fx_idx].append((panel, ExtractionResult(
                panel_type=panel, error="No choices in batch response"
            )))
            continue

        response_text = choices[0].get("message", {}).get("content", "")
        parsed = _repair_json(response_text)
        if parsed is None:
            grouped[fx_idx].append((panel, ExtractionResult(
                panel_type=panel, error=f"JSON parse failed: {response_text[:100]}"
            )))
            continue

        fields = {}
        for key, value in parsed.items():
            if key in ("fields", "extraction_notes"):
                continue
            # Handle nested confidence format: {"value": "...", "conf": "high"}
            if isinstance(value, dict) and "value" in value:
                fields[key] = {
                    "value": value["value"],
                    "bounding_box": None,
                    "extraction_confidence": value.get("conf", "high"),
                }
            else:
                fields[key] = {
                    "value": value,
                    "bounding_box": None,
                    "extraction_confidence": "high",
                }

        grouped[fx_idx].append((panel, ExtractionResult(
            fields=fields, panel_type=panel
        )))

    # Sort each fixture's results by panel order and return just the ExtractionResults
    fixture_results = {}
    for fx_idx, panel_results in grouped.items():
        fixture = fixtures[fx_idx]
        panel_order = [img["panel"] for img in fixture["images"]]
        sorted_results = sorted(
            panel_results,
            key=lambda pr: panel_order.index(pr[0]) if pr[0] in panel_order else 999,
        )
        fixture_results[fx_idx] = [pr[1] for pr in sorted_results]

    return fixture_results


def run_batch_scoring(
    fixtures: list[dict],
    fixture_extractions: dict[int, list[ExtractionResult]],
    comparison_service: ComparisonService,
    merger: ImageMerger,
    scorer: ConfidenceScorer,
) -> list[dict]:
    """Score all fixtures using batch extraction results."""
    results = []
    for fx_idx, fixture in enumerate(fixtures):
        extraction_results = fixture_extractions.get(fx_idx, [])
        if not extraction_results:
            expected = fixture["expected_outcome"]
            results.append({
                "fixture_id": fixture["id"],
                "category": fixture["category"],
                "error": "No batch results for this fixture",
                "expected_status": expected["overall_status"],
                "actual_status": None,
                "correct": False,
                "field_results": {},
            })
            continue

        result = score_fixture(fixture, extraction_results, comparison_service, merger, scorer)
        results.append(result)

    return results


async def run_batch_mode(args, api_key: str, model_name: str, fixtures: list[dict]):
    """Handle --batch mode: submit, poll, and/or score."""
    comparison_service = ComparisonService()
    merger = ImageMerger()
    scorer = ConfidenceScorer()

    if args.batch_results:
        # Retrieve and score a previously submitted batch
        from groq import Groq
        client = Groq(api_key=api_key)

        print(f"Retrieving batch {args.batch_results}...")
        batch = client.batches.retrieve(args.batch_results)

        if batch.status != "completed":
            print(f"Batch status: {batch.status} (not completed yet)")
            if batch.status in ("in_progress", "validating", "finalizing"):
                batch = poll_batch(api_key, args.batch_results)
            else:
                print("Cannot score this batch.")
                return

        batch_results = download_batch_results(api_key, batch)
        if not batch_results:
            return

        # We need the custom_id_map to map results back -- regenerate it
        _, custom_id_map = _regenerate_custom_id_map(fixtures)

        fixture_extractions = batch_results_to_extraction(batch_results, custom_id_map, fixtures)
        results = run_batch_scoring(fixtures, fixture_extractions, comparison_service, merger, scorer)

        start = time.time()
        elapsed = time.time() - start
        print_report(results, model_name + " (batch)", elapsed)

        if args.save:
            _save_results(results, model_name + " (batch)", elapsed)

        return

    # Generate JSONL and submit
    jsonl_path, custom_id_map = generate_batch_jsonl(fixtures, model_name)
    batch_id = submit_batch(api_key, jsonl_path)

    if args.submit_only:
        print(f"\nBatch submitted. ID: {batch_id}")
        print(f"Retrieve results later with: python benchmark.py --batch --results {batch_id}")
        return

    # Poll and score
    start = time.time()
    batch = poll_batch(api_key, batch_id)
    elapsed_poll = time.time() - start

    if batch.status != "completed":
        print(f"Batch ended with status: {batch.status}")
        return

    batch_results = download_batch_results(api_key, batch)
    if not batch_results:
        return

    fixture_extractions = batch_results_to_extraction(batch_results, custom_id_map, fixtures)
    results = run_batch_scoring(fixtures, fixture_extractions, comparison_service, merger, scorer)

    print_report(results, model_name + " (batch)", elapsed_poll)

    if args.save:
        _save_results(results, model_name + " (batch)", elapsed_poll)


def _regenerate_custom_id_map(fixtures: list[dict]) -> tuple[None, dict]:
    """Regenerate the custom_id -> fixture mapping without writing a JSONL file."""
    custom_id_map = {}
    for fx_idx, fixture in enumerate(fixtures):
        fixture_id = fixture["id"]
        _, panels = load_image_paths(fixture)
        for panel in panels:
            custom_id = f"{fixture_id}__{panel}"
            custom_id_map[custom_id] = {
                "fixture_idx": fx_idx,
                "panel": panel,
            }
    return None, custom_id_map


def _save_results(results: list[dict], model_name: str, elapsed: float):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"benchmark_results_{ts}.json",
    )
    with open(out_path, "w") as f:
        json.dump({
            "date": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "elapsed_seconds": elapsed,
            "total": len(results),
            "correct": sum(1 for r in results if r["correct"]),
            "results": results,
        }, f, indent=2)
    print(f"Results saved to: {out_path}")


async def main():
    parser = argparse.ArgumentParser(description="LabelVerify accuracy benchmark")
    parser.add_argument("--fixture", help="Run a single fixture by ID")
    parser.add_argument("--category", help="Run fixtures in a specific category")
    parser.add_argument("--save", action="store_true", help="Save results to JSON file")
    parser.add_argument("--quick", action="store_true", help="Run ~10 representative fixtures")
    parser.add_argument("--no-cache", action="store_true", help="Disable extraction cache")
    parser.add_argument("--clear-cache", action="store_true", help="Wipe cache before running")
    parser.add_argument("--batch", action="store_true", help="Use Groq Batch API (50%% cheaper, no rate limits)")
    parser.add_argument("--submit-only", action="store_true", help="With --batch: submit only, print batch_id")
    parser.add_argument("--results", dest="batch_results", help="With --batch: retrieve + score a previous batch by ID")
    args = parser.parse_args()

    # Validate env
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY env var is required for benchmark (real API calls).")
        sys.exit(1)

    config = Settings()
    model_name = config.llm_model

    # Set up cache
    cache = BenchmarkCache(enabled=not args.no_cache)
    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")

    # Load fixtures
    fixtures = load_fixtures(args.fixture, args.category)

    # Quick subset
    if args.quick:
        fixtures = select_quick_subset(fixtures)
        print(f"Quick mode: selected {len(fixtures)} representative fixture(s)")

    print(f"Running benchmark on {len(fixtures)} fixture(s) with model: {model_name}")
    print()

    if args.batch or args.batch_results:
        await run_batch_mode(args, api_key, model_name, fixtures)
        return

    # Sync mode: run sequentially with cache + throttle
    extraction_service = ExtractionService(api_key=api_key, model=model_name)
    comparison_service = ComparisonService()
    merger = ImageMerger()
    scorer = ConfidenceScorer()
    throttle = RateThrottle()

    results = []
    start = time.time()
    for i, fixture in enumerate(fixtures, 1):
        fid = fixture["id"]
        print(f"[{i}/{len(fixtures)}] {fid}...", end=" ", flush=True)
        try:
            result = await run_single_fixture(
                fixture, extraction_service, comparison_service, merger, scorer,
                cache=cache, throttle=throttle,
            )
            status_mark = "OK" if result["correct"] else "MISMATCH"
            print(f"{status_mark} (expected={result['expected_status']}, got={result['actual_status']})")
            results.append(result)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "fixture_id": fid,
                "category": fixture["category"],
                "error": str(e),
                "expected_status": fixture["expected_outcome"]["overall_status"],
                "actual_status": None,
                "correct": False,
                "field_results": {},
            })

    elapsed = time.time() - start

    # Print report
    print_report(results, model_name, elapsed)
    print(cache.stats())
    print(throttle.stats())

    # Save results
    if args.save:
        _save_results(results, model_name, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
