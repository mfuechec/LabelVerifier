# LabelVerify AI

AI-powered alcohol label verification tool for the TTB (Alcohol and Tobacco Tax and Trade Bureau) Compliance Division. Uses Claude vision to extract label fields from uploaded images and COLA PDFs, then compares them against declared application data using field-specific matching strategies.

## How It Works

1. **Upload** -- Submit COLA PDFs (containing both application data and label artwork) or individual label images
2. **Extract** -- Claude vision reads each label panel and extracts compliance-relevant fields with bounding box coordinates
3. **Compare** -- Field-specific matching strategies (exact, fuzzy, numeric, presence) verify each field against declared values
4. **Re-extract** -- Orchestrator automatically retries extraction for low-confidence or mismatched fields using targeted prompts
5. **Review** -- Color-coded results with annotated bounding boxes; the agent always makes the final call

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite, React Query, React Router |
| Backend | Python 3.13, FastAPI, Pydantic |
| LLM | Anthropic Claude Haiku 4.5 (vision) for both transcription and re-extractions |
| PDF Parsing | pdfplumber + PyMuPDF for COLA application data and embedded label images |
| Database | SQLite (designed for PostgreSQL migration) |
| Matching | rapidfuzz (fuzzy), exact, numeric with unit normalization |
| Annotation | Pillow (bounding box overlays) |

## Project Structure

```
LabelVerifier/
  backend/           # FastAPI application
    app/
      api/routes/    # verify, batch, history, feedback, health endpoints
      services/      # extraction, comparison, compliance, annotation, orchestrator, pdf_parser
      models/        # Pydantic schemas
      db/            # SQLite setup, repository
    data/
      applications/  # COLA PDF test corpus (~59 files)
    tests/           # pytest suite (392 tests)
  frontend/          # React SPA (Vite + TypeScript)
    src/
      components/    # Batch, results, history, shared UI components
      api/           # Axios client, types, error handling
  docs/              # PRD (v2.0), architecture document
  test data/         # Label images organized by category
```

## Local Development

### Prerequisites

- Python 3.13+
- Node.js 18+
- An Anthropic API key

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# Run the server (data directories are created automatically on startup)
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Check health at `GET /api/v1/health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173`. It connects to the backend at `http://localhost:8000` by default (override with `VITE_API_URL` env var).

## Running Tests

### Backend (pytest)

```bash
TESTING=1 backend/.venv/bin/python -m pytest backend/tests/ -x -q
```

392 tests covering:
- Unit tests: normalizer, comparison strategies, compliance checker, annotation, schemas
- Service tests: extraction (mocked LLM), orchestrator (mocked extraction)
- API tests: verify, batch, history, feedback endpoints
- Integration tests: full pipeline across multiple fixture scenarios

### Frontend (Vitest + Testing Library)

```bash
cd frontend
npm test
```

142 tests across 20 files covering:
- Shared components: StatusBadge, ConfidenceBar, ExtractionQualityBadge, LoadingSpinner, ErrorBanner
- Results components: ComparisonRow, ComparisonTable, ReviewBanner, ViewModeToggle, OverrideModal, AgentDecisionBar, ExtractedTextPanel, OverallStatus
- History components: HistoryFilters, HistoryTable
- API hooks: all React Query hooks (useVerify, useVerification, useBatchUpload, etc.)
- Pages: UploadPage, ResultsPage, HistoryPage (integration-level with mocked hooks)

## Matching Strategies

Each field uses a purpose-built matching strategy:

| Strategy | Fields | Details |
|----------|--------|---------|
| **Exact** | Government warning | Whitespace-normalized word-for-word match against canonical text |
| **Fuzzy** | Brand name, class/type, producer/importer name and address, country of origin | rapidfuzz token-based similarity with configurable thresholds |
| **Numeric** | ABV (with proof cross-validation: proof = ABV x 2), net contents (with unit normalization) | Tolerance-based numeric comparison |
| **Presence** | Sulfites declaration | Verifies the statement exists on the label |

Confidence scores: 0-100 per field. Overall = weighted average.
Thresholds: Pass >= 90, Needs Review 70-89, Fail < 70.

## Deployed URLs

- **Frontend:** https://label-verifier-eta.vercel.app
- **Backend:** https://labelverify-backend-production.up.railway.app
- **Health check:** https://labelverify-backend-production.up.railway.app/api/v1/health

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude vision extraction | (required) |
| `LLM_MODEL` | Model to use for initial extraction | `claude-haiku-4-5-20251001` |
| `REEXTRACT_MODEL` | Model to use for re-extractions | `claude-haiku-4-5-20251001` |
| `DATABASE_URL` | SQLite database path | `sqlite:///./data/labelverify.db` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:5173` |

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full implementation-level design, including:
- System diagram and data flow
- 4-phase extraction pipeline (transcription, merging, comparison, re-extraction)
- Database schema
- API endpoint specifications
- Matching strategy details
- Confidence scoring algorithm
