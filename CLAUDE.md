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
- Backend unit tests: pytest
- Frontend tests: Vitest + React Testing Library
- Integration tests: test the full extraction->comparison pipeline against test data images
- Test data is in `test data/` -- organized into 6 folders (good/bad x spirits/wine+beer/warning/photo)
- Create corresponding application data fixtures (JSON) for each test label

## Test Data Categories

| Folder | Images | Tests |
|--------|--------|-------|
| `good spirits` | 18 | Compliant spirits labels (expect Pass) |
| `good wine+beer` | 5 | Compliant wine/beer labels (expect Pass) |
| `bad spirits label` | 18 | Content issues: missing fields, non-English text (expect Fail) |
| `bad spirits photo` | 23 | Extraction challenges: stylized fonts, decorative designs (expect Extraction Uncertain) |
| `bad spirits warning` | 20 | Missing/incorrect government warning (expect Fail on warning field) |
| `bad wine+beer` | 5 | Wine/beer compliance issues (expect Fail) |

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
- **LLM Provider:** Currently `anthropic` with `claude-haiku-4-5-20251001`. To switch back to Groq, set `LLM_PROVIDER=groq` and `LLM_MODEL=meta-llama/llama-4-maverick-17b-128e-instruct`

### Vercel Deployment (Frontend)
- **Frontend URL:** `https://label-verifier-eta.vercel.app`
- **Use the Vercel MCP tools** for all deployment operations. Do NOT use the Vercel CLI or manual dashboard.
- `deploy_to_vercel` -- deploy the frontend
- `list_projects` / `get_project` -- check project config and domains
- `get_deployment_build_logs` -- debug build failures
- `get_runtime_logs` -- debug runtime errors
- If a deploy fails, always check build logs via MCP before attempting fixes
