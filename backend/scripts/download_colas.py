#!/usr/bin/env python3
"""Download fresh COLA applications from TTB public registry for testing.

Usage:
    python scripts/download_colas.py [--count 10] [--output-dir data/applications_fresh]

Downloads printable form HTML + label images, converts to PDF matching
the format expected by COLAPDFParser.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# Disable SSL warnings for TTB's certificate issues
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.ttbonline.gov/colasonline"
SEARCH_URL = f"{BASE_URL}/publicSearchColasBasicProcess.do"
DETAIL_URL = f"{BASE_URL}/viewColaDetails.do"
ATTACHMENT_URL = f"{BASE_URL}/publicViewAttachment.do"


def create_session():
    """Create a session and initialize cookies."""
    session = requests.Session()
    session.verify = False
    # Hit the search page to get session cookies
    session.get(f"{BASE_URL}/publicSearchColasBasic.do")
    return session


def search_colas(session, date_from="01/01/2026", date_to="02/17/2026", max_results=100):
    """Search for COLAs and return list of TTB IDs."""
    resp = session.post(
        f"{SEARCH_URL}?action=search",
        data={
            "searchCriteria.dateCompletedFrom": date_from,
            "searchCriteria.dateCompletedTo": date_to,
            "searchCriteria.productOrFancifulName": "",
            "searchCriteria.productNameSearchType": "E",
        },
    )
    # Extract TTB IDs from results
    ttb_ids = re.findall(r'ttbid=(\d+)', resp.text)
    # Deduplicate preserving order
    seen = set()
    unique = []
    for tid in ttb_ids:
        if tid not in seen:
            seen.add(tid)
            unique.append(tid)
    return unique[:max_results]


def get_form_html(session, ttb_id):
    """Get the printable form HTML for a COLA."""
    resp = session.get(
        f"{DETAIL_URL}?action=publicFormDisplay&ttbid={ttb_id}"
    )
    return resp.text


def extract_label_images(html):
    """Extract label image filenames from the form HTML."""
    # Pattern: publicViewAttachment.do?filename=XXX&filetype=l
    matches = re.findall(
        r'publicViewAttachment\.do\?filename=([^&"]+)&filetype=l',
        html,
    )
    return matches


def download_image(session, filename):
    """Download a label image and return bytes."""
    resp = session.get(
        f"{ATTACHMENT_URL}?filename={urllib.parse.quote(filename)}&filetype=l"
    )
    if resp.headers.get("content-type", "").startswith("image"):
        return resp.content
    # Check if it's actually an image despite wrong content-type
    if resp.content[:3] in (b'\xff\xd8\xff', b'\x89PN', b'GIF'):
        return resp.content
    return None


def extract_field(html, label_pattern):
    """Extract a field value following a label in the HTML."""
    m = re.search(label_pattern + r'</div>\s*</td>\s*<td[^>]*>\s*<div[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL)
    if m:
        val = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return val if val and val != '&nbsp;' else None
    return None


def html_to_pdf_with_images(html, images, ttb_id, output_dir):
    """Convert form HTML + images into a PDF matching our expected format.

    Uses wkhtmltopdf or weasyprint if available, falls back to a simple
    approach using reportlab or img2pdf.
    """
    output_path = Path(output_dir) / f"{ttb_id}.pdf"

    # Approach: save the HTML with embedded images, convert to PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        # Replace image src URLs with local files
        modified_html = html
        for i, (filename, img_bytes) in enumerate(images):
            if img_bytes:
                local_name = f"label_{i}.jpg"
                with open(os.path.join(tmpdir, local_name), "wb") as f:
                    f.write(img_bytes)
                # Replace the URL in HTML
                old_src = f'/colasonline/publicViewAttachment.do?filename={urllib.parse.quote(filename)}&filetype=l'
                modified_html = modified_html.replace(old_src, local_name)
                # Also try unquoted version
                old_src2 = f'/colasonline/publicViewAttachment.do?filename={filename}&filetype=l'
                modified_html = modified_html.replace(old_src2, local_name)

        # Also handle signature images
        modified_html = re.sub(
            r'<img src="/colasonline/publicViewSignature\.do[^"]*"[^>]*>',
            '',
            modified_html,
        )

        html_path = os.path.join(tmpdir, "form.html")
        with open(html_path, "w") as f:
            f.write(modified_html)

        # Try wkhtmltopdf first
        try:
            subprocess.run(
                ["wkhtmltopdf", "--quiet", "--enable-local-file-access", html_path, str(output_path)],
                check=True, capture_output=True, timeout=30,
            )
            return output_path
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        # Try weasyprint
        try:
            import weasyprint
            weasyprint.HTML(filename=html_path).write_pdf(str(output_path))
            return output_path
        except ImportError:
            pass

        # Fallback: just save images as PDF pages using Pillow
        try:
            from PIL import Image
            import io

            pil_images = []
            for filename, img_bytes in images:
                if img_bytes:
                    img = Image.open(io.BytesIO(img_bytes))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    pil_images.append(img)

            if pil_images:
                pil_images[0].save(
                    str(output_path), "PDF", save_all=True,
                    append_images=pil_images[1:] if len(pil_images) > 1 else [],
                )
                print(f"  Warning: PDF contains only label images (no form data). "
                      f"wkhtmltopdf or weasyprint needed for full form.")
                return output_path
        except ImportError:
            pass

        print(f"  Error: No PDF converter available. Install wkhtmltopdf or weasyprint.")
        return None


def download_cola(session, ttb_id, output_dir):
    """Download a single COLA application as PDF."""
    print(f"  Fetching {ttb_id}...")

    # Need to view the detail page first (session state)
    session.get(f"{DETAIL_URL}?action=publicDisplaySearchBasic&ttbid={ttb_id}")

    # Get printable form
    html = get_form_html(session, ttb_id)

    # Extract and download label images
    image_filenames = extract_label_images(html)
    if not image_filenames:
        print(f"  Skipping {ttb_id}: no label images")
        return None

    images = []
    for fname in image_filenames:
        img_bytes = download_image(session, fname)
        images.append((fname, img_bytes))
        if img_bytes:
            print(f"    Downloaded image: {fname} ({len(img_bytes)} bytes)")
        else:
            print(f"    Failed to download: {fname}")

    if not any(img for _, img in images):
        print(f"  Skipping {ttb_id}: no images downloaded")
        return None

    # Convert to PDF
    pdf_path = html_to_pdf_with_images(html, images, ttb_id, output_dir)
    if pdf_path:
        print(f"  Saved: {pdf_path}")
    return pdf_path


def main():
    parser = argparse.ArgumentParser(description="Download fresh COLA applications from TTB")
    parser.add_argument("--count", type=int, default=10, help="Number of COLAs to download")
    parser.add_argument("--output-dir", default="data/applications_fresh", help="Output directory")
    parser.add_argument("--date-from", default="01/01/2026", help="Search date from (MM/DD/YYYY)")
    parser.add_argument("--date-to", default="02/17/2026", help="Search date to (MM/DD/YYYY)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Creating session...")
    session = create_session()

    print(f"Searching for COLAs ({args.date_from} to {args.date_to})...")
    ttb_ids = search_colas(session, args.date_from, args.date_to, max_results=args.count * 3)
    print(f"Found {len(ttb_ids)} COLAs")

    # Filter out IDs we already have
    existing = {p.stem for p in Path("data/applications").glob("*.pdf")} if Path("data/applications").exists() else set()
    new_ids = [tid for tid in ttb_ids if tid not in existing]
    print(f"After filtering existing: {len(new_ids)} new COLAs")

    downloaded = 0
    for ttb_id in new_ids:
        if downloaded >= args.count:
            break
        result = download_cola(session, ttb_id, output_dir)
        if result:
            downloaded += 1
        time.sleep(1)  # Be polite

    print(f"\nDone! Downloaded {downloaded} COLAs to {output_dir}")


if __name__ == "__main__":
    main()
