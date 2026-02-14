# Architecture Document: LabelVerify AI

**Version:** 1.0
**Date:** February 14, 2026
**Status:** Final
**Source PRD:** `TTB_LabelVerify_PRD.md` v2.0

---

## 1. System Overview

LabelVerify AI is a two-tier web application: a React SPA frontend and a Python FastAPI backend. The backend orchestrates a pipeline that extracts text from label images via Claude's vision API, compares extracted fields against declared application data, generates annotated label images, and returns structured results for agent review.

```
User (Browser)
    |
    v
[React SPA] -- Vercel
    |
    v  (HTTPS REST)
[FastAPI API] -- Railway/Render
    |
    +---> [Claude Vision API] -- Anthropic
    +---> [SQLite DB] -- local file
```

All state lives in the database. The API is stateless and horizontally scalable. The frontend is a static SPA with no server-side rendering.

---

## 2. Data Flow: Core Verification Pipeline

This is the primary path for a single-label verification in Assist Mode.

```
1. Agent uploads label image(s) + application data
2. API receives multipart upload, stores images, parses application data
3. ImageGrouper associates images by panel type (front/back/other)
4. For each image panel:
   a. Send to Claude Vision API with extraction prompt
   b. Receive structured JSON: field values + bounding regions
5. FieldNormalizer standardizes extracted values (units, casing, whitespace)
6. ImageMerger combines fields across panels, flags conflicts
7. ComparisonEngine runs field-by-field matching:
   - Exact match: government warning vs. canonical text
   - Fuzzy match: brand, class/type, producer, address, country
   - Numeric match: ABV (+ proof cross-check), net contents
   - Presence check: sulfites declaration
8. ComplianceChecker validates mandatory fields by beverage type
9. ConfidenceScorer calculates per-field and overall scores
10. AnnotationEngine overlays bounding boxes on original images
11. Results assembled and persisted to database
12. Response returned to frontend: comparison table + annotated image(s)
13. Agent reviews, confirms/overrides, submits final decision
```

**Target latency:** Steps 3-11 must complete within 5 seconds for a single label. The Claude Vision API call (step 4) is the latency bottleneck -- expect 2-4 seconds. All other steps should be sub-second.

---

## 3. API Design

### 3.1 Base URL & Conventions

- Base: `/api/v1`
- All responses: `{"data": ...}` on success, `{"error": "message", "detail": "..."}` on failure
- Authentication: None for prototype (future: JWT or session-based)
- Content types: `application/json` for data, `multipart/form-data` for uploads

### 3.2 Endpoints

#### Upload & Verification

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/verify` | Single-label verification (images + application data) |
| `POST` | `/verify/batch` | Batch verification (multiple images + CSV) |
| `GET` | `/verify/{session_id}` | Get verification result by session ID |
| `GET` | `/verify/{session_id}/annotated/{panel}` | Get annotated image for a panel (front/back/other) |

#### Review & Feedback

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/verifications` | List verification history (paginated, filterable) |
| `PATCH` | `/verify/{session_id}/fields/{field_name}` | Agent override on a single field |
| `POST` | `/verify/{session_id}/decision` | Submit final agent decision (pass/fail/review) |
| `POST` | `/verify/{session_id}/feedback` | Submit AI correct/incorrect feedback |

#### Utility

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (API + DB + Claude API connectivity) |

### 3.3 Key Request/Response Shapes

#### `POST /api/v1/verify` -- Single Label Verification

**Request** (multipart/form-data):
```
images[]: File[]              # 1-3 image files
panels[]: string[]            # "front", "back", "other" (parallel array with images)
application_data: string      # JSON string of application data
```

**Response:**
```json
{
  "data": {
    "session_id": "uuid",
    "status": "pass | needs_review | fail",
    "overall_confidence": 87,
    "beverage_type": "distilled_spirits",
    "fields": [
      {
        "field_name": "brand_name",
        "declared_value": "STONE'S THROW",
        "extracted_value": "Stone's Throw",
        "status": "match",
        "confidence": 95,
        "match_strategy": "fuzzy",
        "bounding_box": {
          "panel": "front",
          "x": 120, "y": 45, "width": 280, "height": 60
        }
      },
      {
        "field_name": "government_warning",
        "declared_value": null,
        "extracted_value": "GOVERNMENT WARNING: (1) According to...",
        "status": "match",
        "confidence": 98,
        "match_strategy": "exact",
        "bounding_box": {
          "panel": "back",
          "x": 30, "y": 400, "width": 340, "height": 120
        }
      }
    ],
    "annotated_images": {
      "front": "/api/v1/verify/{session_id}/annotated/front",
      "back": "/api/v1/verify/{session_id}/annotated/back"
    },
    "created_at": "2026-02-14T10:30:00Z"
  }
}
```

#### `GET /api/v1/verifications` -- List History

**Query params:** `?status=pass|fail|needs_review&beverage_type=distilled_spirits&brand=stone&page=1&per_page=20`

**Response:**
```json
{
  "data": {
    "items": [
      {
        "session_id": "uuid",
        "application_id": "APP-2026-12345",
        "brand_name": "STONE'S THROW",
        "beverage_type": "distilled_spirits",
        "status": "pass",
        "overall_confidence": 95,
        "agent_decision": "confirmed",
        "created_at": "2026-02-14T10:30:00Z"
      }
    ],
    "total": 142,
    "page": 1,
    "per_page": 20
  }
}
```

#### `PATCH /api/v1/verify/{session_id}/fields/{field_name}` -- Agent Override

**Request:**
```json
{
  "override_status": "match | content_mismatch | field_missing",
  "note": "Optional agent note explaining override"
}
```

---

## 4. Database Schema

SQLite for prototype. All tables use UUID primary keys for future PostgreSQL migration compatibility.

### 4.1 Tables

```sql
-- Top-level verification session
CREATE TABLE verification_sessions (
    id TEXT PRIMARY KEY,                    -- UUID
    application_id TEXT,                    -- From application data
    beverage_type TEXT NOT NULL,            -- beer | wine | distilled_spirits
    status TEXT NOT NULL DEFAULT 'pending', -- pending | pass | needs_review | fail
    overall_confidence REAL,
    agent_decision TEXT,                    -- confirmed | overridden | null
    agent_notes TEXT,
    ai_correct INTEGER,                    -- 1 = correct, 0 = incorrect, null = no feedback
    created_at TEXT NOT NULL,               -- ISO 8601
    updated_at TEXT NOT NULL
);

-- Declared application data
CREATE TABLE applications (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES verification_sessions(id),
    brand_name TEXT,
    class_type TEXT,
    alcohol_content TEXT,
    net_contents TEXT,
    producer_name TEXT,
    producer_address TEXT,
    country_of_origin TEXT,
    importer_name TEXT,
    importer_address TEXT,
    has_sulfites_declaration INTEGER DEFAULT 0,  -- boolean
    raw_json TEXT                                 -- Original submitted JSON
);

-- Uploaded label images
CREATE TABLE label_images (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES verification_sessions(id),
    panel_type TEXT NOT NULL,       -- front | back | other
    file_path TEXT NOT NULL,        -- Relative path to stored image
    mime_type TEXT NOT NULL,
    file_size INTEGER,
    annotated_path TEXT             -- Path to annotated version (generated)
);

-- Per-field extraction results
CREATE TABLE extracted_fields (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES verification_sessions(id),
    image_id TEXT REFERENCES label_images(id),
    field_name TEXT NOT NULL,       -- brand_name, government_warning, etc.
    extracted_value TEXT,
    confidence REAL,                -- 0-100 extraction confidence
    bbox_x REAL,
    bbox_y REAL,
    bbox_width REAL,
    bbox_height REAL,
    panel_type TEXT                 -- Which panel this was extracted from
);

-- Per-field comparison results
CREATE TABLE comparison_results (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES verification_sessions(id),
    field_name TEXT NOT NULL,
    declared_value TEXT,
    extracted_value TEXT,
    match_strategy TEXT NOT NULL,   -- exact | fuzzy | numeric | presence | compliance
    status TEXT NOT NULL,           -- match | content_mismatch | field_missing | extraction_uncertain
    confidence REAL,                -- 0-100 comparison confidence
    override_status TEXT,           -- Agent override: match | content_mismatch | field_missing | null
    override_note TEXT
);

-- Agent feedback records
CREATE TABLE agent_feedback (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES verification_sessions(id),
    ai_correct INTEGER NOT NULL,    -- 1 or 0
    field_name TEXT,                 -- Optional: which field was wrong
    note TEXT,
    created_at TEXT NOT NULL
);
```

### 4.2 Indexes

```sql
CREATE INDEX idx_sessions_status ON verification_sessions(status);
CREATE INDEX idx_sessions_beverage ON verification_sessions(beverage_type);
CREATE INDEX idx_sessions_created ON verification_sessions(created_at);
CREATE INDEX idx_sessions_app_id ON verification_sessions(application_id);
CREATE INDEX idx_applications_session ON applications(session_id);
CREATE INDEX idx_images_session ON label_images(session_id);
CREATE INDEX idx_extracted_session ON extracted_fields(session_id);
CREATE INDEX idx_comparison_session ON comparison_results(session_id);
CREATE INDEX idx_feedback_session ON agent_feedback(session_id);
```

---

## 5. Service Layer

### 5.1 VerificationOrchestrator

The central coordinator. Receives a verification request, delegates to services, assembles the result.

```python
class VerificationOrchestrator:
    async def verify_single(
        self,
        images: list[UploadFile],
        panels: list[str],
        application_data: ApplicationData
    ) -> VerificationResult:
        # 1. Store images
        # 2. Group by panel
        # 3. Extract fields from each panel via ExtractionService
        # 4. Merge fields across panels via ImageMerger
        # 5. Compare against application data via ComparisonService
        # 6. Run compliance checks
        # 7. Calculate confidence scores
        # 8. Generate annotated images via AnnotationService
        # 9. Persist everything to DB
        # 10. Return VerificationResult
```

### 5.2 ExtractionService

Sends label images to Claude Vision API and parses the structured response.

```python
class ExtractionService:
    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str
    ) -> ExtractionResult:
        # 1. Encode image as base64
        # 2. Build Claude Vision prompt (see Section 6)
        # 3. Call Anthropic API with image + prompt
        # 4. Parse structured JSON response
        # 5. Return ExtractionResult with fields + bounding regions
```

**Key design decision:** One API call per image panel. For a front+back label, this means 2 parallel Claude calls. We parallelize these with `asyncio.gather()` to stay within the 5-second budget.

### 5.3 ComparisonService

Dispatches each field to the appropriate matching strategy.

```python
class ComparisonService:
    def compare_fields(
        self,
        extracted: dict[str, ExtractedField],
        declared: ApplicationData,
        beverage_type: str
    ) -> list[ComparisonResult]:
        # For each required field (based on beverage_type):
        #   1. Look up extracted value
        #   2. Dispatch to strategy: exact/fuzzy/numeric/presence
        #   3. Calculate confidence
        #   4. Determine status: match/content_mismatch/field_missing/extraction_uncertain
```

**Matching strategy implementations:**

```python
# Exact: government warning
def exact_match(extracted: str, canonical: str) -> tuple[str, float]:
    normalized_ext = normalize_whitespace(extracted)
    normalized_can = normalize_whitespace(canonical)
    if normalized_ext == normalized_can:
        return ("match", 100.0)
    # Check if GOVERNMENT WARNING: prefix is all caps
    # Check word-by-word similarity for partial credit
    ...

# Fuzzy: brand name, producer, etc.
def fuzzy_match(extracted: str, declared: str, threshold: float = 0.85) -> tuple[str, float]:
    # Normalize case, strip punctuation, collapse spaces
    # Calculate similarity ratio (e.g., SequenceMatcher or rapidfuzz)
    # Return match/mismatch based on threshold
    ...

# Numeric: ABV, net contents
def numeric_match(extracted: str, declared: str) -> tuple[str, float]:
    # Parse numeric value and unit from both strings
    # Normalize units (mL, cL, L, fl oz)
    # Compare numeric values with tolerance (e.g., 0.1% for ABV)
    # If proof present, cross-validate: proof == ABV * 2
    ...

# Presence: sulfites declaration
def presence_check(extracted: str | None, required: bool) -> tuple[str, float]:
    # If required and found -> match
    # If required and not found -> field_missing
    # If not required -> match (N/A)
    ...
```

### 5.4 ComplianceChecker

Validates mandatory field presence by beverage type, independent of application data.

```python
class ComplianceChecker:
    MANDATORY_FIELDS: dict[str, list[str]] = {
        "distilled_spirits": [
            "brand_name", "class_type", "alcohol_content",
            "net_contents", "producer_name", "government_warning"
        ],
        "wine": [
            "brand_name", "class_type", "alcohol_content",
            "net_contents", "producer_name", "government_warning"
        ],
        "beer": [
            "brand_name", "class_type",
            "net_contents", "producer_name", "government_warning"
            # ABV not auto-required for beer -- flagged as needs_review if absent
        ]
    }

    def check_compliance(
        self,
        extracted_fields: dict[str, ExtractedField],
        beverage_type: str
    ) -> list[ComplianceIssue]:
        # Check each mandatory field is present
        # Check government warning exact match against canonical
        # Flag beer ABV absence as needs_review (not fail)
```

### 5.5 AnnotationService

Generates annotated label images with color-coded bounding boxes.

```python
class AnnotationService:
    def annotate_image(
        self,
        image_path: str,
        field_results: list[ComparisonResult]
    ) -> str:
        # 1. Load original image (Pillow)
        # 2. For each field with bounding box:
        #    - Green border (3px) for match
        #    - Red border for content_mismatch or field_missing
        #    - Yellow border for extraction_uncertain
        #    - Label with field name above the box
        # 3. Save annotated image to annotated_path
        # 4. Return path
```

### 5.6 ImageMerger

Combines extraction results from multiple panels into a single field set.

```python
class ImageMerger:
    def merge_panels(
        self,
        panel_results: dict[str, ExtractionResult]
    ) -> MergedExtraction:
        # For each field:
        #   - If found in only one panel -> use it
        #   - If found in multiple panels with same value -> use either, note source
        #   - If found in multiple panels with different values -> flag as conflict,
        #     prefer front panel, set status to needs_review
```

---

## 6. LLM Prompt Strategy

### 6.1 Extraction Prompt

Sent to Claude Vision API with the label image.

```
You are an alcohol beverage label analysis system for the US TTB (Alcohol and
Tobacco Tax and Trade Bureau). Extract all compliance-relevant fields from this
label image.

Return a JSON object with the following structure. For each field found, include
the extracted text and an approximate bounding box (x, y, width, height as
percentages of image dimensions, 0-100). If a field is not found, set its value
to null and omit the bounding_box.

{
  "fields": {
    "brand_name": {
      "value": "string or null",
      "bounding_box": {"x": 0, "y": 0, "width": 0, "height": 0}
    },
    "class_type": { ... },
    "alcohol_content": { ... },
    "alcohol_proof": { ... },
    "net_contents": { ... },
    "producer_name": { ... },
    "producer_address": { ... },
    "country_of_origin": { ... },
    "importer_name": { ... },
    "importer_address": { ... },
    "government_warning": { ... },
    "sulfites_declaration": { ... }
  },
  "extraction_notes": "Any observations about image quality, readability, or
                       ambiguous text"
}

Rules:
- Extract text EXACTLY as it appears on the label (preserve capitalization)
- For alcohol_content, extract the percentage value including format
  (e.g., "45% Alc./Vol.")
- For alcohol_proof, extract proof if separately stated (e.g., "90 Proof")
- For government_warning, extract the COMPLETE warning text verbatim
- Bounding boxes are percentage-based: x=0,y=0 is top-left; x=100,y=100 is
  bottom-right
- If text is partially obscured or hard to read, extract your best reading and
  note the issue in extraction_notes
```

### 6.2 API Call Structure

```python
response = await anthropic_client.messages.create(
    model="claude-sonnet-4-5-20250929",  # Best speed/quality for extraction
    max_tokens=2048,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64_image
                    }
                },
                {
                    "type": "text",
                    "text": EXTRACTION_PROMPT
                }
            ]
        }
    ]
)
```

**Model choice:** Claude Sonnet 4.5 for extraction -- it's the best balance of speed and vision quality. Opus would be more accurate but too slow for the 5-second budget. Haiku would be faster but less reliable on stylized labels.

### 6.3 Prompt Design Rationale

- **Percentage-based bounding boxes** -- avoids needing to know pixel dimensions in the prompt; the backend converts to pixel coordinates using actual image dimensions
- **Separate alcohol_content and alcohol_proof** -- proof is redundant but useful as a cross-check
- **extraction_notes field** -- gives the LLM an escape valve for ambiguous cases, which we surface as "Extraction Uncertain" status
- **"Extract EXACTLY as it appears"** -- prevents the LLM from normalizing text (we normalize ourselves in FieldNormalizer)

---

## 7. Frontend Architecture

### 7.1 Component Tree

```
App
  +-- Layout (header, nav)
  +-- Routes:
      +-- UploadPage (default route: /)
      |     +-- ImageUploadZone (front/back/other drop zones)
      |     +-- ApplicationDataForm (manual entry)
      |     +-- ApplicationDataUpload (JSON file picker)
      |     +-- VerifyButton
      |     +-- LoadingState (progress indicator during extraction)
      |
      +-- ResultsPage (/verify/:sessionId)
      |     +-- SplitView (resizable two-panel layout)
      |     |     +-- AnnotatedLabelViewer (left panel)
      |     |     |     +-- ImageCanvas (zoom/pan, bounding box overlay)
      |     |     |     +-- PanelTabs (front/back/other)
      |     |     |
      |     |     +-- ComparisonPanel (right panel)
      |     |           +-- OverallStatus (pass/needs_review/fail badge)
      |     |           +-- ComparisonTable
      |     |           |     +-- ComparisonRow (per field)
      |     |           |           +-- FieldStatus (color-coded badge)
      |     |           |           +-- OverrideButton
      |     |           |           +-- ConfidenceBar
      |     |           |
      |     |           +-- AgentDecisionBar (confirm/override + notes)
      |     |           +-- FeedbackWidget (AI correct/incorrect)
      |     |
      |     +-- OverrideModal (note input when overriding a field)
      |
      +-- BatchPage (/batch)
      |     +-- BatchUploadZone (images + CSV)
      |     +-- BatchQueue
      |           +-- BatchQueueItem (status, brand, click to drill in)
      |           +-- BatchProgress (overall progress bar)
      |           +-- BatchFilters (sort/filter by status)
      |
      +-- HistoryPage (/history)
            +-- HistoryFilters (status, beverage type, date range, search)
            +-- HistoryTable
                  +-- HistoryRow (click to navigate to ResultsPage)
```

### 7.2 State Management

- **React Query (TanStack Query)** for server state: verification results, history list, batch queue status
- **Local component state** for UI concerns: zoom level, active panel tab, override modal open/closed
- No global state store (Redux, Zustand) needed -- the app is server-driven and React Query handles caching/invalidation

### 7.3 Key UI Interactions

**AnnotatedLabelViewer:**
- Canvas-based rendering with HTML5 Canvas or a library like `react-zoom-pan-pinch`
- Bounding boxes drawn as colored rectangles with labels
- Clicking a bounding box highlights the corresponding row in ComparisonTable (and vice versa)
- Zoom/pan via mouse wheel and drag

**ComparisonTable:**
- Rows are color-coded by status (green/red/yellow left border)
- Hover on a row highlights the corresponding bounding box on the image
- Override button opens a modal for the agent to change status and add a note
- Confidence displayed as a small horizontal bar or numeric badge

---

## 8. File Storage

For the prototype, uploaded and annotated images are stored on the local filesystem:

```
data/
  uploads/
    {session_id}/
      front.jpg
      back.jpg
      other.jpg
  annotated/
    {session_id}/
      front_annotated.png
      back_annotated.png
```

The `label_images` table stores relative paths. For production, this would migrate to blob storage (Azure Blob, S3).

---

## 9. Error Handling

| Scenario | Behavior |
|----------|----------|
| Claude API timeout (>5s) | Return partial results with `extraction_uncertain` for unprocessed fields. Log timeout. |
| Claude API rate limit | Queue and retry with exponential backoff (max 2 retries). Return 503 if exhausted. |
| Unreadable image | Return `extraction_uncertain` for all fields with note "Image could not be processed." |
| Invalid application data | Return 422 with field-level validation errors. |
| Database write failure | Return 500, log error. Verification not persisted but results still returned to UI. |
| Image too large | Reject at upload with 413. Max 10MB per image. |

---

## 10. Performance Budget

| Step | Target | Notes |
|------|--------|-------|
| Image upload + storage | < 200ms | Async file write |
| Claude Vision API call | 2-4s | Primary bottleneck. Parallel calls for multi-panel. |
| Field normalization | < 50ms | String operations only |
| Panel merging | < 10ms | In-memory dict merge |
| Comparison engine | < 100ms | Fuzzy matching with rapidfuzz |
| Compliance checks | < 10ms | Lookup table |
| Annotation generation | < 500ms | Pillow image operations |
| DB persistence | < 100ms | SQLite local file |
| **Total single-label** | **< 5s** | Parallel Claude calls are the key optimization |

For batch processing: labels are processed asynchronously via background tasks (FastAPI BackgroundTasks or a task queue). The API returns immediately with a batch ID. The frontend polls for progress.

---

## 11. Technology Choices & Rationale

| Choice | Rationale |
|--------|-----------|
| **FastAPI** | Async-native (critical for parallel Claude calls), auto-generates OpenAPI docs, Pydantic validation, excellent Python ecosystem for image processing |
| **Claude Sonnet 4.5** | Best speed/quality balance for vision extraction. Opus too slow for 5s budget. Haiku too unreliable on stylized text. |
| **SQLite** | Zero-config for prototype. Single-file database. Easy to inspect during development. Schema designed for drop-in PostgreSQL migration. |
| **Pillow** | Standard Python image library. Sufficient for bounding box overlays. No heavy dependencies. |
| **rapidfuzz** | Fast fuzzy string matching in Python (C++ bindings). Better performance than difflib SequenceMatcher. |
| **React Query** | Eliminates boilerplate for server state. Built-in caching, polling (for batch progress), and optimistic updates (for overrides). |
| **Vite** | Fast dev server and build tool for React. TypeScript-first. |
| **Percentage-based bounding boxes** | LLM returns coordinates as percentages. Frontend/backend convert to pixels using actual image dimensions. Avoids prompt needing to know image size. |

---

## 12. Security Considerations (Prototype)

- No authentication (prototype scope). Future: add JWT/session auth.
- API keys (`ANTHROPIC_API_KEY`) stored in environment variables, never in code or client.
- CORS restricted to the frontend domain.
- File uploads validated: max 10MB, allowed MIME types only (image/jpeg, image/png, image/tiff, application/pdf).
- No PII beyond what appears on the label.
- SQLite file not exposed via any API endpoint.

---

## 13. Directory Structure (Detailed)

```
LabelVerifier/
  frontend/
    src/
      components/
        upload/
          ImageUploadZone.tsx
          ApplicationDataForm.tsx
          ApplicationDataUpload.tsx
        results/
          AnnotatedLabelViewer.tsx
          ImageCanvas.tsx
          PanelTabs.tsx
          ComparisonTable.tsx
          ComparisonRow.tsx
          OverallStatus.tsx
          AgentDecisionBar.tsx
          FeedbackWidget.tsx
          OverrideModal.tsx
        batch/
          BatchUploadZone.tsx
          BatchQueue.tsx
          BatchProgress.tsx
        history/
          HistoryTable.tsx
          HistoryFilters.tsx
        shared/
          Layout.tsx
          StatusBadge.tsx
          ConfidenceBar.tsx
          LoadingSpinner.tsx
      pages/
        UploadPage.tsx
        ResultsPage.tsx
        BatchPage.tsx
        HistoryPage.tsx
      api/
        client.ts            # Axios/fetch wrapper
        verifications.ts     # React Query hooks for verification endpoints
        types.ts             # Shared TypeScript types
      lib/
        constants.ts         # Canonical warning text, status colors, etc.
      App.tsx
      main.tsx
    public/
    index.html
    vite.config.ts
    tsconfig.json
    package.json

  backend/
    app/
      main.py                # FastAPI app factory, CORS, middleware
      config.py              # Settings from environment variables
      api/
        __init__.py
        routes/
          verify.py          # /verify, /verify/{id}, /verify/batch
          feedback.py        # /verify/{id}/feedback, /verify/{id}/decision
          history.py         # /verifications
          health.py          # /health
        dependencies.py      # Shared dependencies (DB session, services)
      models/
        database.py          # SQLAlchemy models / table definitions
        schemas.py           # Pydantic request/response models
      services/
        orchestrator.py      # VerificationOrchestrator
        extraction.py        # ExtractionService (Claude Vision)
        comparison.py        # ComparisonService + matching strategies
        compliance.py        # ComplianceChecker
        annotation.py        # AnnotationService (Pillow)
        merger.py            # ImageMerger
        normalizer.py        # FieldNormalizer
      db/
        setup.py             # SQLite connection, table creation
    tests/
      conftest.py
      test_extraction.py
      test_comparison.py
      test_compliance.py
      test_annotation.py
      test_merger.py
      test_normalizer.py
      test_api/
        test_verify.py
        test_history.py
        test_feedback.py
      fixtures/
        sample_applications.json
        expected_extractions/  # Expected JSON output per test image
    requirements.txt
    Dockerfile

  test data/                  # Provided label images (read-only)
  docs/
    architecture.md           # This document
    TTB_LabelVerify_PRD.md
  ttb_architecture.mermaid
  CLAUDE.md
  .env.example
  .gitignore
  README.md
```
