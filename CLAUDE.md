# LabelVerify AI

## Project Overview

AI-powered alcohol label verification tool for TTB Compliance Division. Standalone prototype (no COLA integration). Operates in Assist Mode: AI extracts and compares, agent makes the final call.

**PRD:** `docs/TTB_LabelVerify_PRD.md` (v2.0 -- source of truth for all requirements)
**Architecture:** `docs/architecture.md` (v1.0 -- implementation-level design)
**System Diagram:** `ttb_architecture.mermaid`

## Tech Stack

- **Frontend:** React SPA (TypeScript), deployed to Vercel or Netlify
- **Backend:** Python + FastAPI, deployed to Railway, Render, or Fly.io
- **LLM:** Anthropic Claude (vision) for combined OCR + structured field extraction -- no separate OCR service
- **Database:** SQLite for prototype (design for PostgreSQL migration)
- **Image Annotation:** Server-side or client-side canvas overlay for bounding boxes

## Project Structure

```
LabelVerifier/
  frontend/          # React SPA (Vite + TypeScript)
  backend/           # FastAPI application
    app/
      api/           # Route handlers
      core/          # Config, dependencies
      models/        # SQLAlchemy / Pydantic models
      services/      # Business logic
        extraction/  # LLM vision extraction pipeline
        comparison/  # Field matching engine
        annotation/  # Bounding box overlay generation
      db/            # Database setup, migrations
  tests/             # Test suite (mirrors backend/frontend structure)
  test data/         # Provided label images (do not modify)
  docs/              # PRD, architecture, additional docs
```

## Development Rules

### General
- Follow TDD: write failing test first, confirm red, implement to green, then refactor
- Run the full test suite after every feature implementation
- Keep the 5-second single-label processing target in mind for all pipeline decisions
- Never hardcode API keys -- use environment variables via `.env` (gitignored)
- All API endpoints return consistent error shapes: `{"error": "message", "detail": "..."}`

### LLM Extraction
- Use Claude's vision API with structured output prompting
- Send label images as base64-encoded content blocks
- Prompt should request JSON output with field values AND approximate bounding regions
- Normalize all extracted text before comparison (trim, collapse whitespace)
- For multi-image labels, extract each panel independently then merge in the ImageMerger service

### Matching Engine
- Each field uses a specific matching strategy -- never use a generic string compare:
  - **Exact:** Government warning only (after whitespace normalization)
  - **Fuzzy:** Brand name, class/type, producer name/address, importer name/address, country of origin
  - **Numeric:** ABV (with proof cross-validation: proof = ABV x 2), net contents (with unit normalization)
  - **Presence:** Sulfites declaration (just verify it exists)
- Confidence scores: 0-100 per field. Overall = weighted average.
- Thresholds: Pass >= 90, Needs Review 70-89, Fail < 70

### Government Warning -- Canonical Text
The exact text to match against (after whitespace normalization):

```
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
```

Rules: "GOVERNMENT WARNING:" must be ALL CAPS. Full statement must be word-for-word. Normalize whitespace/line breaks before comparison. Bold detection is out of scope.

### Mandatory Fields by Beverage Type

| Field | Spirits | Wine | Beer |
|-------|:-------:|:----:|:----:|
| Brand name | Req | Req | Req |
| Class/type | Req | Req | Req |
| ABV | Req | Req | Varies* |
| Net contents | Req | Req | Req |
| Producer/bottler/importer | Req | Req | Req |
| Country of origin | If imported | If imported | If imported |
| Government warning | Req | Req | Req |
| Sulfites | N/A | If applicable | N/A |

*Beer ABV: flag absence as "Needs Review", not auto-fail.

### Frontend
- Single-screen core workflow: upload -> review -> decide
- Large click targets, clear labels, no hidden actions (agents aged 25-65+)
- WCAG 2.1 AA compliance
- Upload interface: labeled drop zones for Front / Back / Other
- Annotated label viewer: canvas overlay with green/red/yellow bounding boxes
- Comparison table: clickable rows highlight corresponding bounding box

### Testing

#### 1. Unit/Integration Tests (pytest)
```
TESTING=1 backend/.venv/bin/python -m pytest backend/tests/ -x -q
```
- Mocked LLM calls, tests logic in isolation (extraction, comparison, orchestrator, compliance, etc.)
- **Run after every code change.** All tests must pass before deploying.

#### 2. End-to-End Batch Verification (deployed API)
The real test corpus is **`backend/data/applications/`** -- COLA PDFs containing both application data and label images. This is the primary integration test.

```bash
# Submit all COLA PDFs (skip OMB template files):
APP_DIR="backend/data/applications"
ARGS=""
for f in "$APP_DIR"/*.pdf; do
    [[ "$(basename "$f")" == OMB* ]] && continue
    ARGS="$ARGS -F 'cola_pdfs[]=@$f'"
done
eval curl -s -X POST '"https://labelverify-backend-production.up.railway.app/api/v1/batch"' $ARGS | python3 -m json.tool

# Poll for results:
curl -s "https://labelverify-backend-production.up.railway.app/api/v1/batch/{BATCH_ID}" | python3 -m json.tool
```

- **Run after every deploy.** Exercises the full pipeline: PDF parsing, image extraction, LLM vision calls, field merging, re-extractions, comparison, compliance, scoring, DB persistence.
- PDFs with no embedded label images are automatically skipped (the ~26KB text-only COLAs).
- Review each session's field-level results via `GET /api/v1/verify/{session_id}`.
- Focus on: brand_name accuracy, government_warning match, overall status progression.

#### 3. Legacy Benchmark (extraction + comparison only)
```
cd backend && .venv/bin/python benchmark.py [--quick] [--fixture ID]
```
- Uses `backend/tests/fixtures/sample_applications.json` with raw images from `test data/`
- Does NOT exercise orchestrator re-extraction logic (brand confirmation, warning re-extract, etc.)
- Useful for measuring raw LLM extraction accuracy, not full pipeline correctness

#### Test Corpus

| Source | Files | Purpose |
|--------|-------|---------|
| `backend/data/applications/*.pdf` | ~23 COLA PDFs | **Primary.** End-to-end via batch API |
| `backend/tests/` | pytest suite | Unit/integration with mocked LLM |
| `test data/` (6 folders) | Raw label images | Legacy benchmark only |

## Failure Categories

1. **Match** -- field matches within strategy tolerance (green)
2. **Content Mismatch** -- field extracted but wrong value (red)
3. **Field Missing** -- required field not found on label (red)
4. **Extraction Uncertain** -- field area found but low confidence (yellow, needs review)

## Deployment

- Frontend: `npm run build` -> deploy to Vercel
- Backend: Dockerized FastAPI -> deploy to Railway
- Environment variables: `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `DATABASE_URL`, `ALLOWED_ORIGINS`
- HTTPS everywhere, CORS configured for frontend domain

### Railway Deployment (Backend)
- **Project:** `labelverify-backend`
- **Service:** `labelverify-backend`
- **Public URL:** `https://labelverify-backend-production.up.railway.app`
- **Root directory:** `backend` (Railway builds from this subdirectory)
- **Dockerfile:** `backend/Dockerfile`
- Use `railway` CLI (installed) for all deployment operations
- `railway status` -- check project/service/environment
- `railway variables` -- list env vars
- `railway variables --set "KEY=value"` -- set env vars (auto-triggers redeploy)
- `railway logs` -- view deployment logs
- `railway up` -- manual deploy. **CRITICAL: Run from the project root (`LabelVerifier/`), NOT from `backend/`.** Railway applies `RAILWAY_ROOT_DIRECTORY=backend` itself, so running from `backend/` causes it to look for `backend/backend/` which doesn't exist.
- **LLM Provider:** Currently `anthropic` with `claude-sonnet-4-5-20250929`. To switch back to Groq, set `LLM_PROVIDER=groq` and `LLM_MODEL=meta-llama/llama-4-maverick-17b-128e-instruct`

### Vercel Deployment (Frontend)
- **Frontend URL:** `https://label-verifier-eta.vercel.app`
- **Use the Vercel MCP tools** for all deployment operations. Do NOT use the Vercel CLI or manual dashboard.
- `deploy_to_vercel` -- deploy the frontend
- `list_projects` / `get_project` -- check project config and domains
- `get_deployment_build_logs` -- debug build failures
- `get_runtime_logs` -- debug runtime errors
- If a deploy fails, always check build logs via MCP before attempting fixes
