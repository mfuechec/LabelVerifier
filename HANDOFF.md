# LabelVerifier Handoff — 2026-02-16

## What Was Accomplished

### Model Upgrade
- Switched default LLM from `claude-haiku-4-5-20251001` to `claude-sonnet-4-5-20250929`
- Railway env var `LLM_MODEL` set to `claude-sonnet-4-5-20250929`
- All 6 LLM calls use `temperature=0` for deterministic extraction

### Matching/Extraction Fixes (6 total)
1. **Style designator acceptance** — Single ALL-CAPS word in COLA fanciful_name (e.g. "ACHOLADO", "ITALIA") treated as variety code, not brand mismatch
2. **Importer single-word containment** — "Niche" matches "NICHE W. & S., NICHE IMPORT CO." at 95%
3. **Country re-extraction** — New `reextract_country_of_origin()` with dedicated prompt, triggered when country is null and product appears imported
4. **Brand name partial_ratio fallback** — When standard fuzzy_match fails for brand_name, tries `partial_ratio` (handles COLA typos like "VIJO TONEL" vs "Pisco Viejo Tonel")
5. **Net contents magnitude check** — Discrepancies >5x flagged as `extraction_uncertain` instead of `content_mismatch` (catches OCR errors like 50mL vs 750mL)
6. **Composition statement fallback** — When fanciful_name field mismatches, checks composition_statement for the declared fanciful name (from prior session)

### Test Suite
- 307 tests, all passing
- Fixed shadowed test class: renamed duplicate `TestCompareFieldsSpecialtyClass` → `TestSpecialtyClassAdminCodes` (was hiding 7 tests)

## Current Batch Results (15 labels processed)

| Status | Count | Labels |
|--------|-------|--------|
| **pass** | 8 | Howling Moon x3, Barenjager x2, Jacques Cardin, Vijo Tonel, Viejo Tonel |
| **needs_review** | 2 | Ecstasy (83%, producer mismatch), Tomasello (0%, no label image) |
| **fail** | 5 | Lenz Moser x4, Barenjager Honey & Pear |

**Previous run (Haiku, no fixes): 4 pass, 2 needs_review, 9 fail**

## Remaining Failures — Root Causes

### Lenz Moser Wines (4 labels)
- **2 labels at ~57% confidence**: Multiple fields missing (brand, class_type, ABV, net_contents). These are complex multi-panel Austrian wine labels — Sonnet is failing to extract several fields.
- **2 labels at ~95% confidence**: Only failing field is class_type. Extracted class is "STILL WINE" or similar, but COLA declares a more specific type. The fuzzy match scores ~70%, just below 85% threshold.

### Barenjager Honey & Pear (81%)
- **Fanciful name**: COLA declares "HONEY & PEAR" but label prominently shows "Bärenjäger". The specialty_class_match checks fanciful_name first, finds mismatch.
- **Net contents**: OCR reads 50mL instead of 750mL. Correctly flagged as `extraction_uncertain` (magnitude check working).

## Potential Next Improvements

1. **Wine class_type normalization** — "STILL WINE" / "TABLE WINE" / "RED WINE" should fuzzy-match COLA wine class types better. Could add wine-specific class normalization similar to `normalize_class_type()` for spirits.
2. **Multi-panel extraction for Lenz Moser** — The ~57% labels are missing basic fields. May need investigation into why Sonnet fails on these specific label layouts. Could be image quality or panel ordering.
3. **Barenjager HONEY & PEAR fanciful** — This is a multi-word declared fanciful that's genuinely different from the brand. The style designator fix only handles single-word codes. May need a broader "fanciful is a product descriptor" pattern.
4. **Empty extraction detection** — Plan exists at `~/.claude/plans/sequential-scribbling-rocket.md` for detecting when all fields come back null (Tomasello case). Not yet implemented but would improve UX.

## Key Files

| File | What Changed |
|------|-------------|
| `backend/app/services/extraction.py` | Model default, `COUNTRY_REEXTRACT_PROMPT`, `reextract_country_of_origin()`, `temperature=0` on all calls |
| `backend/app/services/comparison.py` | Style designator logic, single-word containment, brand partial_ratio fallback, net contents magnitude check |
| `backend/app/services/orchestrator.py` | Country re-extraction trigger wired into pipeline |
| `backend/tests/test_comparison.py` | 5 new test classes, renamed shadowed class |
| `CLAUDE.md` | Updated LLM model reference to Sonnet |

## Batch Test Command

```bash
# Submit all COLA PDFs:
APP_DIR="backend/data/applications"
ARGS=""
for f in "$APP_DIR"/*.pdf; do
    [[ "$(basename "$f")" == OMB* ]] && continue
    ARGS="$ARGS -F 'cola_pdfs[]=@$f'"
done
eval curl -s -X POST '"https://labelverify-backend-production.up.railway.app/api/v1/batch"' $ARGS | python3 -m json.tool

# Poll for results (replace BATCH_ID):
curl -s "https://labelverify-backend-production.up.railway.app/api/v1/batch/{BATCH_ID}" | python3 -m json.tool

# Get field details for a session:
curl -s "https://labelverify-backend-production.up.railway.app/api/v1/verify/{SESSION_ID}" | python3 -m json.tool
```

## Latest Commit
`535e563` — Switch to Sonnet, add 6 matching/extraction fixes for batch accuracy
