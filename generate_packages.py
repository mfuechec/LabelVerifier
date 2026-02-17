#!/usr/bin/env python3
"""Generate test data packages: label images + application PDFs organized by scenario category."""

import json
import os
import re
import shutil

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FIXTURES_PATH = os.path.join(PROJECT_ROOT, "backend", "tests", "fixtures", "sample_applications.json")
TEST_DATA_ROOT = os.path.join(PROJECT_ROOT, "test data")
SCENARIOS_ROOT = os.path.join(TEST_DATA_ROOT, "scenarios")

# Map fixture category to source image folder
CATEGORY_TO_FOLDER = {
    "good spirits": "good spirits",
    "good wine+beer": "good wine+beer",
    "bad spirits label": "bad spirits label",
    "bad spirits photo": "bad spirits photo",
    "bad spirits warning": "bad spirits warning",
    "bad wine+beer": "bad wine+beer",
}

# Scenario categories that map to output subdirectories
SCENARIO_CATEGORIES = [
    "pass",
    "fail_mismatch",
    "fail_missing",
    "needs_review",
    "edge_cases",
]


def slugify(name: str) -> str:
    """Convert brand name to a filesystem-friendly slug."""
    slug = name.lower()
    slug = slug.replace("&", "and")
    slug = slug.replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def generate_pdf(filepath: str, app_data: dict) -> None:
    """Generate a single-page form-style PDF with application data."""
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, height - 1 * inch, "TTB Label Verification - Application Data")

    # Separator line
    c.setLineWidth(1.5)
    c.line(1 * inch, height - 1.15 * inch, width - 1 * inch, height - 1.15 * inch)

    # Field data
    fields = [
        ("Application ID", app_data.get("application_id")),
        ("Brand Name", app_data.get("brand_name")),
        ("Class/Type", app_data.get("class_type")),
        ("Alcohol Content", app_data.get("alcohol_content")),
        ("Net Contents", app_data.get("net_contents")),
        ("", ""),  # blank line
        ("Producer Name", app_data.get("producer_name")),
        ("Producer Address", app_data.get("producer_address")),
        ("", ""),  # blank line
        ("Country of Origin", app_data.get("country_of_origin")),
        ("Importer Name", app_data.get("importer_name")),
        ("Importer Address", app_data.get("importer_address")),
        ("", ""),  # blank line
        ("Beverage Type", _format_beverage_type(app_data.get("beverage_type"))),
        ("Sulfites Declared", "Yes" if app_data.get("has_sulfites_declaration") else "No"),
    ]

    y = height - 1.6 * inch
    label_x = 1 * inch
    value_x = 3.2 * inch
    line_height = 0.3 * inch

    for label, value in fields:
        if label == "" and value == "":
            y -= line_height * 0.5
            continue

        display_value = value if value else "--"

        c.setFont("Helvetica-Bold", 11)
        c.drawString(label_x, y, f"{label}:")

        c.setFont("Helvetica", 11)
        # Handle long values by truncating if needed
        if len(str(display_value)) > 60:
            c.setFont("Helvetica", 9)
        c.drawString(value_x, y, str(display_value))

        y -= line_height

    c.save()


def _format_beverage_type(btype: str | None) -> str:
    if not btype:
        return "--"
    return {
        "distilled_spirits": "Distilled Spirits",
        "wine": "Wine",
        "beer": "Beer",
    }.get(btype, btype)


def _fixture_slug(fixture: dict) -> str:
    """Generate a unique slug for a fixture from its ID."""
    # Use the fixture ID (minus the category prefix) as the slug
    fixture_id = fixture["id"]
    # Remove category prefix like "pass-", "mismatch-", "missing-", "review-", "edge-"
    for prefix in ["pass-", "mismatch-", "missing-", "review-", "edge-"]:
        if fixture_id.startswith(prefix):
            return fixture_id[len(prefix):]
    return slugify(fixture["application_data"]["brand_name"])


def main():
    with open(FIXTURES_PATH) as f:
        data = json.load(f)

    fixtures = data["fixtures"]

    # Clean and create output dirs
    if os.path.exists(SCENARIOS_ROOT):
        shutil.rmtree(SCENARIOS_ROOT)
    for cat in SCENARIO_CATEGORIES:
        os.makedirs(os.path.join(SCENARIOS_ROOT, cat), exist_ok=True)

    counts = {cat: 0 for cat in SCENARIO_CATEGORIES}
    errors = []

    for fixture in fixtures:
        category = fixture["category"]
        scenario = fixture["scenario_category"]
        app_data = fixture["application_data"]
        slug = _fixture_slug(fixture)

        # Create subfolder under scenario category
        pkg_dir = os.path.join(SCENARIOS_ROOT, scenario, slug)
        os.makedirs(pkg_dir, exist_ok=True)

        # Copy images from source folder
        source_folder = os.path.join(TEST_DATA_ROOT, CATEGORY_TO_FOLDER[category])
        for img_info in fixture["images"]:
            src = os.path.join(source_folder, img_info["filename"])
            dst = os.path.join(pkg_dir, img_info["filename"])
            if os.path.exists(src):
                shutil.copy2(src, dst)
            else:
                errors.append(f"  Missing image: {src}")

        # Generate PDF
        pdf_path = os.path.join(pkg_dir, "application.pdf")
        generate_pdf(pdf_path, app_data)

        counts[scenario] = counts.get(scenario, 0) + 1

    # Summary
    total = sum(counts.values())
    print(f"Generated {total} test data packages in test data/scenarios/:")
    for cat in SCENARIO_CATEGORIES:
        print(f"  {cat}/: {counts[cat]} packages")

    if errors:
        print(f"\nWarnings ({len(errors)}):")
        for e in errors:
            print(e)
    else:
        print("\nAll images copied successfully.")


if __name__ == "__main__":
    main()
