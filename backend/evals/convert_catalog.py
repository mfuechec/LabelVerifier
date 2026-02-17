#!/usr/bin/env python3
"""Convert test data/label_catalog.json to eval_ground_truth.json.

One-time conversion script. Run from the backend directory:
    python -m evals.convert_catalog
"""

import json
from pathlib import Path


# Mapping from catalog government_warning status to expected field status
GOV_WARNING_STATUS_MAP = {
    "present_correct": "match",
    "present_incorrect": "content_mismatch",
    "missing": "field_missing",
    "present_uncertain": "extraction_uncertain",
}

# Fields that appear in ApplicationData (fed to orchestrator as declared values)
APPLICATION_DATA_FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_of_origin",
    "importer_name",
    "importer_address",
]


def infer_panel(filename: str) -> str:
    """Infer panel type from filename keywords."""
    lower = filename.lower()
    if "back" in lower:
        return "back"
    if "other" in lower or "side" in lower or "neck" in lower:
        return "other"
    return "front"


def convert_product(entry: dict) -> dict:
    """Convert a single label_catalog entry to eval ground truth product."""
    label_values = entry["label_values"]

    # Build application_data (declared values for orchestrator)
    application_data = {}
    for field in APPLICATION_DATA_FIELDS:
        val = label_values.get(field)
        if val is not None:
            application_data[field] = val

    application_data["beverage_type"] = entry["beverage_type"]

    # Determine source_of_product
    is_imported = bool(
        label_values.get("country_of_origin")
        or label_values.get("importer_name")
    )
    application_data["source_of_product"] = "imported" if is_imported else "domestic"

    # Determine has_sulfites_declaration
    application_data["has_sulfites_declaration"] = label_values.get("sulfites_declaration") is not None

    # Build expected_fields: per-field expected status after pipeline
    expected_fields = {}

    # For declared fields, expect "match" if the field has a value in the catalog
    for field in APPLICATION_DATA_FIELDS:
        val = label_values.get(field)
        if val is not None:
            expected_fields[field] = "match"
        # If field is None, we don't set an expectation (it's not declared)

    # Government warning is special - not in ApplicationData but has expected status
    gov_warning_status = label_values.get("government_warning", "missing")
    expected_fields["government_warning"] = GOV_WARNING_STATUS_MAP.get(
        gov_warning_status, "field_missing"
    )

    # Sulfites declaration
    if label_values.get("sulfites_declaration") is not None:
        expected_fields["sulfites_declaration"] = "match"

    # Infer expected overall status from usable_for and gov_warning
    usable_for = entry.get("usable_for", [])
    if "pass" in usable_for:
        expected_status = "pass"
    elif "needs_review" in usable_for:
        expected_status = "needs_review"
    elif "fail_missing" in usable_for or "fail_mismatch" in usable_for:
        expected_status = "fail"
    elif "edge_cases" in usable_for:
        # Edge cases may pass or fail depending on pipeline behavior
        expected_status = "needs_review"
    else:
        expected_status = "needs_review"

    # Infer panels from filenames
    image_files = entry["image_files"]
    panels = [infer_panel(f) for f in image_files]

    return {
        "id": entry["label_id"],
        "source_folder": entry["source_folder"],
        "image_files": image_files,
        "panels": panels,
        "application_data": application_data,
        "expected_status": expected_status,
        "expected_fields": expected_fields,
        "notes": entry.get("notes", ""),
    }


def main():
    catalog_path = Path(__file__).parent.parent.parent / "test data" / "label_catalog.json"
    output_path = Path(__file__).parent / "eval_ground_truth.json"

    if not catalog_path.exists():
        print(f"Catalog not found: {catalog_path}")
        return

    with open(catalog_path) as f:
        catalog = json.load(f)

    products = [convert_product(entry) for entry in catalog]

    ground_truth = {
        "version": "2.0",
        "products": products,
    }

    with open(output_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Converted {len(products)} products -> {output_path}")


if __name__ == "__main__":
    main()
