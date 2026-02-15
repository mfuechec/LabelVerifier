# LabelVerify AI

AI-powered alcohol label verification tool for TTB (Alcohol and Tobacco Tax and Trade Bureau) compliance. Uses Llama vision (via Groq) to extract label fields and compare them against declared application data.

## How It Works

1. **Upload** label images (front, back, other panels) and enter application data
2. **Extract** -- Llama vision reads the label and extracts compliance-relevant fields
3. **Compare** -- Field-specific matching strategies verify each field against declared values
4. **Review** -- Color-coded results with annotated bounding boxes; agent makes final call

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite, React Query, React Router |
| Backend | Python 3.13, FastAPI, Pydantic |
| LLM | Groq (Llama 4 Scout vision) for OCR + structured extraction |
| Database | SQLite (designed for PostgreSQL migration) |
| Matching | rapidfuzz (fuzzy), exact, numeric with unit normalization |
| Annotation | Pillow (bounding box overlays) |

## Project Structure

```
LabelVerifier/
  backend/           # FastAPI application
    app/
      api/routes/    # verify, history, feedback, health endpoints
      services/      # extraction, comparison, compliance, merger, annotation, orchestrator
      models/        # Pydantic schemas, database helpers
      db/            # SQLite setup
    tests/           # pytest suite (171 tests)
  frontend/          # React SPA (Vite + TypeScript)
    src/
      components/    # Upload, comparison table, annotated viewer, etc.
      api/           # Axios client + React Query hooks
  docs/              # PRD, architecture document
  test data/         # Label images organized by category
```

## Local Development

### Prerequisites

- Python 3.13+
- Node.js 18+
- A Groq API key (free at [console.groq.com](https://console.groq.com))

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env and set your GROQ_API_KEY

# Create data directories
mkdir -p data/uploads data/annotated

# Run the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Check health at `GET /api/v1/health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies API requests to the backend.

## Running Tests

### Backend (pytest)

```bash
cd backend
source venv/bin/activate
python -m pytest -v
```

171 tests covering:
- Unit tests: normalizer, comparison strategies, compliance checker, merger, annotation, schemas
- Service tests: extraction (mocked API), orchestrator (mocked extraction)
- API tests: verify, history, feedback endpoints
- Integration tests: full pipeline across 8 fixture scenarios

### Frontend

```bash
cd frontend
npm test
```

## Deployed URLs

- **Frontend:** https://label-verifier-eta.vercel.app
- **Backend:** https://labelverify-backend-production.up.railway.app
- **Repository:** https://github.com/mfuechec/LabelVerifier

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full implementation-level design, including:
- System diagram and data flow
- Database schema
- API endpoint specifications
- Matching strategy details
- Confidence scoring algorithm

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key for Llama vision extraction | (required) |
| `DATABASE_URL` | SQLite database path | `sqlite:///./data/labelverify.db` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:5173` |
