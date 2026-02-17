# Evaluation Framework

End-to-end pipeline evaluation for LabelVerifier. Calls `VerificationOrchestrator.verify_single()` per product and compares the full pipeline output against ground truth.

## Quick Start

```bash
cd backend

# 1. Generate ground truth from label_catalog.json (one-time)
python -m evals.convert_catalog

# 2. Run full evaluation
python -m evals.run_eval

# 3. Quick smoke test (2 products)
python -m evals.run_eval --max-products 2

# 4. Filter by product ID or source folder
python -m evals.run_eval --filter "angels-envy"
python -m evals.run_eval --filter "good spirits"

# 5. Save detailed JSON results
python -m evals.run_eval --output results.json
```

## Files

- **convert_catalog.py** - Converts `test data/label_catalog.json` to `eval_ground_truth.json`
- **eval_ground_truth.json** - Per-product ground truth (generated, do not hand-edit)
- **run_eval.py** - Main evaluation script

## Ground Truth Format

```json
{
  "version": "2.0",
  "products": [{
    "id": "angels-envy",
    "source_folder": "good spirits",
    "image_files": ["Angels Envy burbon front.jpg", "Angels Envy burbon back.jpg"],
    "panels": ["front", "back"],
    "application_data": {
      "brand_name": "Angel's Envy",
      "class_type": "Kentucky Straight Bourbon Whiskey...",
      "alcohol_content": "43.3% Alc./Vol. (86.6 Proof)",
      "net_contents": "750 mL",
      "beverage_type": "distilled_spirits",
      "source_of_product": "domestic",
      "has_sulfites_declaration": false
    },
    "expected_status": "pass",
    "expected_fields": {
      "government_warning": "match",
      "brand_name": "match",
      "alcohol_content": "match"
    },
    "notes": "Clear front+back, all fields readable"
  }]
}
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--ground-truth`, `-g` | `evals/eval_ground_truth.json` | Path to ground truth file |
| `--output`, `-o` | (none) | Save detailed JSON results |
| `--concurrency`, `-c` | 3 | Max parallel products |
| `--max-products`, `-n` | (all) | Limit products for quick tests |
| `--filter`, `-f` | (none) | Filter by product ID or source_folder |

## Metrics

- **Status accuracy** - % products where expected_status == actual_status
- **Status confusion matrix** - Shows pass->fail, pass->needs_review, etc.
- **Per-field assertion accuracy** - % of field status expectations met
- **Cost** - Total and per-product USD
- **Performance** - Total and per-product time, LLM calls
