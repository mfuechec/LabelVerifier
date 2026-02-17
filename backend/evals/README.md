# Evaluation Framework

This directory contains tools for evaluating LLM extraction accuracy.

## Quick Start

```bash
cd backend

# Run evaluation against ground truth
python -m evals.run_eval

# Generate template for new test images
python -m evals.run_eval --generate-template "test data/**/*.jpg"

# Save detailed results to JSON
python -m evals.run_eval --output results.json
```

## Files

- **ground_truth_schema.json** - JSON schema for ground truth data format
- **ground_truth_data.json** - Actual ground truth entries (edit this!)
- **run_eval.py** - Main evaluation script

## Adding Ground Truth Data

1. Add label images to `test data/` or `data/applications/`
2. Generate a template:
   ```bash
   python -m evals.run_eval --generate-template "test data/0. Spirits Complete/*.jpg"
   ```
3. Edit `ground_truth_template.json` to fill in expected values
4. Copy entries to `ground_truth_data.json`
5. Run evaluation to verify

## Metrics

The evaluation reports:

- **Accuracy**: % of fields correctly extracted
- **Precision**: When we extract a value, how often is it correct?
- **Recall**: Of fields that should have values, how many did we find?
- **F1**: Harmonic mean of precision and recall
- **Confidence Calibration**: When model says "high confidence", how often is it actually correct?

## Tips

- Focus on fields with <90% accuracy for prompt improvements
- Check confidence calibration to detect overconfident extractions
- Use `--output results.json` to track accuracy over time
- Re-run after prompt changes to check for regressions
