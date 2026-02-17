# Product Requirements Document: AI-Powered Alcohol Label Verification App

**Project Name:** LabelVerify AI
**Author:** Mark Fuechec
**Date:** February 14, 2026
**Version:** 2.0
**Status:** Final Draft
**Stakeholders:** TTB Compliance Division (Sarah Chen, Deputy Director), IT Systems (Marcus Williams), Compliance Agents (Dave Morrison, Jenny Park)

---

## 1. Executive Summary

The TTB Compliance Division reviews approximately 150,000 alcohol label applications per year with a team of 47 agents. The majority of agent time is spent on routine matching tasks -- verifying that information on submitted label artwork matches the corresponding application data. This tool automates the extraction and comparison process using AI, freeing agents to focus on nuanced compliance decisions.

LabelVerify AI is a standalone proof-of-concept that demonstrates AI-powered label verification without integrating into the existing COLA system. It operates in Assist Mode: the AI extracts, compares, and annotates, but the agent always makes the final call. If successful, the prototype will inform future procurement and integration decisions.

---

## 2. Problem Statement

Agents currently perform manual, visual comparison between label artwork and application data for every submission. This process is repetitive, error-prone at scale, and creates a bottleneck -- especially during peak season when large importers submit 200-300 applications at once. A previous vendor pilot failed due to unacceptable processing times (30-40 seconds per label), teaching the division that any solution must return results in approximately 5 seconds to achieve adoption.

---

## 3. Goals & Success Criteria

### Primary Goals

- Reduce average per-label review time from 5-10 minutes to under 2 minutes for routine applications
- Achieve 95%+ extraction accuracy across all required label fields
- Return verification results within 5 seconds for single-label processing
- Provide a UI that agents of all technical comfort levels can use without training

### Success Criteria

- Agents voluntarily adopt the tool over manual review for routine labels
- Batch processing capability handles 200+ labels in a single upload session
- Government warning verification catches all formatting and wording deviations
- Agent feedback indicates trust in AI recommendations

---

## 4. User Personas

### Sarah Chen -- Deputy Director of Label Compliance
Needs to see throughput improvements and reduced backlog. Cares about team adoption and ease of use. Champions the project to leadership. Benchmark: "something my mother could figure out."

### Dave Morrison -- Senior Compliance Agent (28 years)
Skeptical of automation. Needs to see that the tool respects nuance (e.g., cosmetic case differences vs. actual mismatches). Won't adopt anything that makes his workflow harder. The tool must support his judgment, not replace it.

### Jenny Park -- Junior Compliance Agent (8 months)
Enthusiastic about modernization. Currently uses a printed checklist. Would benefit most from automated extraction and comparison. Wants the tool to handle imperfect or stylized label images.

### Marcus Williams -- IT Systems Administrator
Concerned about security, network restrictions, and infrastructure compatibility. Needs the solution to work within government network constraints (firewall, blocked domains). Evaluating for potential future integration with COLA.

---

## 5. Core Features

### 5.1 Label Image Upload & Extraction

**Description:** Agents upload one or more label images (front, back, or other panels). The system extracts all text and identifies required compliance fields using an LLM vision pipeline.

**Primary Input Type:** The standard COLA workflow involves submitted **label artwork** (clean, flat design files). This is the primary input the system is optimized for. Handling of photographic images (angled shots, glare, poor lighting) is a stretch goal.

**Requirements:**
- Accept common image formats (JPEG, PNG, TIFF, PDF)
- Support multi-image labels via labeled upload zones (see 5.1.1)
- Extract field values with bounding box coordinates for annotation
- Return extraction results within 5 seconds for a single label

**Fields to Extract:**
- Brand name
- Class/type designation
- Alcohol content (ABV), including proof if present
- Net contents
- Name and address of bottler/producer/importer
- Country of origin (for imports)
- Government health warning statement
- Contains sulfites declaration (where applicable)
- Appellation/origin designation (wine only, where applicable)

#### 5.1.1 Multi-Image Grouping

**Single-label mode:** The upload interface provides labeled drop zones -- "Front Label," "Back Label," and "Other" -- so the agent can associate multiple images with a single application. All images in the group are processed together and fields are merged across panels.

**Batch mode:** A CSV column maps each application row to one or more image filenames. Images are uploaded as a batch alongside the CSV. The system groups images by application ID.

### 5.2 Application Data Input

**Description:** Agents provide the declared application data to compare against the extracted label data. For the prototype, this simulates what would come from the COLA system in production.

**Input Methods:**
- Manual form entry (agent types in declared values)
- JSON file upload (for single applications)
- CSV file upload (for batch applications)

**Application Data Schema:**
```json
{
  "application_id": "string",
  "brand_name": "string",
  "class_type": "string",
  "alcohol_content": "string (e.g., '45%' or '45% (90 Proof)')",
  "net_contents": "string (e.g., '750 mL')",
  "producer_name": "string",
  "producer_address": "string",
  "country_of_origin": "string (optional, required for imports)",
  "importer_name": "string (optional)",
  "importer_address": "string (optional)",
  "beverage_type": "beer | wine | distilled_spirits",
  "has_sulfites_declaration": "boolean (optional, primarily wine)",
  "label_images": ["string (filename, for batch CSV mapping)"]
}
```

### 5.3 Comparison & Verification Engine

**Description:** The system compares extracted label data against declared application data and checks compliance requirements. Different matching strategies are applied based on field type.

#### 5.3.1 Field-to-Strategy Mapping

| Field | Strategy | Notes |
|-------|----------|-------|
| Brand name | Fuzzy | Case, punctuation, spacing tolerance. "STONE'S THROW" matches "Stone's Throw." |
| Class/type | Fuzzy | Normalize casing and common abbreviations. "Kentucky Straight Bourbon Whiskey" matches "KENTUCKY STRAIGHT BOURBON WHISKEY." |
| Alcohol content (ABV) | Numeric | Normalize "Alc./Vol.", "ABV", "Alcohol by Volume", etc. Extract percentage as primary value. If proof is present, cross-validate: proof should equal ABV x 2. "45% Alc./Vol. (90 Proof)" matches "45%." |
| Net contents | Numeric | Normalize mL/cL/L/fl oz. "750 mL" matches "750ML" matches "75cL." |
| Producer/bottler name | Fuzzy | Case, punctuation, spacing, common abbreviations (Co., Corp., LLC). |
| Producer/bottler address | Fuzzy | Abbreviation tolerance: "St." vs "Street", "Ste." vs "Suite", state abbreviations. |
| Country of origin | Fuzzy | "Jalisco, Mexico" matches declared "Mexico." Region-within-country is acceptable. |
| Importer name | Fuzzy | Same rules as producer name. |
| Importer address | Fuzzy | Same rules as producer address. |
| Government warning | Exact | Word-for-word match against canonical text. "GOVERNMENT WARNING:" must be in all caps. Whitespace/line breaks normalized before comparison. See Section 5.3.3. |
| Contains sulfites | Presence | Verify declaration exists on label if `has_sulfites_declaration` is true. Exact wording flexible ("Contains Sulfites", "CONTAINS SULFITES"). |

#### 5.3.2 Compliance Checks (Independent of Application Data)

These checks run against the extracted label data alone, regardless of what the application declares:

- All mandatory fields for the beverage type are present on the label (see 5.3.4)
- Government warning statement is present, exact, and properly formatted
- ABV is displayed in an acceptable format
- Net contents are stated
- Producer/bottler or importer information is present
- Country of origin is present for imported products

#### 5.3.3 Government Warning Statement -- Canonical Text

The following is the federally mandated health warning that must appear on all alcohol beverage containers:

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

**Verification rules:**
- The text "GOVERNMENT WARNING:" must appear in ALL CAPS
- The full statement must be word-for-word correct
- Whitespace, line breaks, and hyphenation are normalized before comparison (labels often wrap text)
- **Bold detection limitation:** TTB requires "GOVERNMENT WARNING:" to be bold and/or conspicuous. Detecting bold formatting from an image is unreliable via OCR. The prototype verifies all-caps and exact wording. Bold detection is documented as a known limitation.

#### 5.3.4 Mandatory Fields by Beverage Type

| Field | Distilled Spirits | Wine | Beer |
|-------|:-----------------:|:----:|:----:|
| Brand name | Required | Required | Required |
| Class/type designation | Required | Required | Required |
| Alcohol content (ABV) | Required | Required | Varies* |
| Net contents | Required | Required | Required |
| Producer/bottler/importer | Required | Required | Required |
| Country of origin | If imported | If imported | If imported |
| Government warning | Required | Required | Required |
| Sulfites declaration | N/A | If applicable | N/A |

*Beer ABV requirements vary. The prototype flags absence as "Needs Review" rather than an automatic failure.

#### 5.3.5 Confidence Scoring

- Each field comparison produces a confidence score (0-100)
- Overall verification confidence is the weighted average of field-level scores
- Configurable thresholds determine status routing:
  - **Pass** (>= 90 confidence, all mandatory fields present, no mismatches)
  - **Needs Review** (70-89 confidence, or fuzzy match near threshold)
  - **Fail** (< 70 confidence, or any mandatory field missing/mismatched)

#### 5.3.6 Failure Categories

The system classifies each field result into one of four categories, derived from the test data taxonomy:

1. **Match** -- Field extracted and matches declared value within strategy tolerance
2. **Content Mismatch** -- Field extracted but does not match declared value (e.g., wrong ABV, different brand spelling)
3. **Field Missing** -- Required field not found on the label at all (e.g., no government warning present)
4. **Extraction Uncertain** -- Field area identified but OCR/LLM confidence is low (e.g., stylized/decorative fonts, overlapping text, poor contrast). Routed to human review.

### 5.4 Annotated Label Output

**Description:** The original label image is annotated with color-coded bounding boxes showing where each required field was found and its verification status.

**Color Coding:**
- **Green** -- Field found and matches application data (Match)
- **Red** -- Field found but does not match, or required field missing (Content Mismatch / Field Missing)
- **Yellow** -- Field found but needs human review (Extraction Uncertain / low confidence)

**Requirements:**
- Bounding boxes must be positioned accurately on the original image
- Each box is labeled with the field name
- Clicking a box in the UI highlights the corresponding row in the comparison table
- Agents can zoom and pan the annotated image
- For multi-image labels, each image panel is annotated independently and displayed in a tabbed or side-by-side view

### 5.5 Field-by-Field Comparison Table

**Description:** A structured table showing each required field with the declared value (from application), extracted value (from label), match status, and confidence score.

**Columns:**
- Field Name
- Declared Value (application)
- Extracted Value (label)
- Status (Match / Content Mismatch / Field Missing / Extraction Uncertain)
- Confidence Score
- Agent Action (Override / Confirm / Flag)

**Interaction:** Clicking a row highlights the corresponding bounding box on the annotated label. Agent can override any field status with one click and optionally add a note.

### 5.6 Batch Processing

**Description:** Support for processing multiple label applications in a single session, addressing peak-season workloads of 200-300 applications.

**Requirements:**
- Upload multiple label images and a corresponding CSV of application data
- CSV maps application IDs to image filenames for multi-image grouping
- Process labels asynchronously with a progress tracker
- Display results as a queue with sortable/filterable status columns
- Allow agents to click into any individual result for detailed review
- Prioritize flagged/failed items at the top of the queue

### 5.7 Review History

**Description:** A persistent record of all processed verifications, enabling agents to review past work and track their queue.

**Requirements:**
- List all verification sessions with timestamp, brand name, beverage type, status, and agent
- Filter by status (Pass / Fail / Needs Review / Agent Override), date range, beverage type, brand name
- Click into any record to view the full annotated label and comparison table
- Agent override status is tracked and visible (AI recommendation vs. agent final decision)
- Search by application ID or brand name

---

## 6. Human-in-the-Loop Design

### 6.1 Assist Mode (Prototype Default)

The prototype operates exclusively in Assist Mode:

- AI displays extraction results, comparison table, and annotated label
- Results are clearly framed as **recommendations**, not decisions
- Agent makes the final pass/fail determination for every application
- Agent can confirm or override each field-level result
- Override reasons are captured (optional free-text notes)

**Rationale:** Assist Mode builds agent trust, collects feedback data, and preserves agent authority -- addressing Dave's concern that the tool "support his judgment, not replace it."

### 6.2 Agent Feedback Loop

**Description:** Agents can mark AI results as correct or incorrect, building a labeled dataset over time.

**Requirements:**
- One-click "AI Correct" / "AI Incorrect" per verification
- Optional field-level feedback (which specific field was wrong)
- Free-text notes field for context on overrides
- Feedback is stored with the verification record
- Aggregated feedback feeds into accuracy metrics

### 6.3 Future Modes (Out of Scope for Prototype)

The architecture supports two additional modes for future deployment. These are documented here for architectural awareness but will not be implemented in the prototype.

**Shadow Mode** -- AI processes labels silently in the background. Results are stored and compared against agent decisions after the fact. Produces accuracy metrics without disrupting existing workflow. Recommended for 2-4 weeks as a pre-deployment evaluation.

**Autonomous Mode** -- AI automatically processes and approves high-confidence verifications. Low-confidence results and mismatches are routed to human review. Requires accumulated accuracy data and leadership sign-off before activation.

### 6.4 Future Evaluation Features (Out of Scope for Prototype)

- QA sampling with blind review (configurable random sampling, reviewer assesses without seeing AI results)
- Accuracy dashboard with trend metrics (overall rate, per-field breakdown, false positive/negative rates, beverage type breakdown)
- Export verification report as PDF/JSON

---

## 7. Non-Functional Requirements

### Performance
- Single-label verification: results returned within 5 seconds
- Batch processing: 200+ labels queued and processing initiated within 30 seconds
- UI responsive and usable during batch processing (non-blocking)

### Usability
- No training required for basic usage
- Interface must be accessible to non-technical users (agents aged 25-65+)
- Large click targets, clear labels, obvious primary actions
- Minimal navigation -- core workflow (upload, review, decide) achievable from a single screen
- Accessible (WCAG 2.1 AA compliance for government use)

### Security & Compliance
- No PII storage in the prototype beyond what's on the label
- Prototype does not require FedRAMP compliance but architecture should be compatible
- All data transmission over HTTPS
- API keys and credentials stored server-side, never exposed to the client

### Reliability
- Graceful degradation if AI service is unavailable (agents can still view uploaded images and enter results manually)
- Clear error messaging for failed extractions or processing timeouts
- Retry logic for transient API failures (up to 2 retries with exponential backoff)

---

## 8. Technical Architecture Summary

### Frontend
- React single-page application deployed to **Vercel or Netlify**
- Drag-and-drop upload interface with labeled drop zones (Front / Back / Other)
- Interactive annotated label viewer with zoom/pan (canvas-based overlay)
- Responsive comparison table with inline agent actions

### Backend API
- RESTful API deployed to **Railway, Render, or Fly.io**
- Verification orchestration: receives images + application data, coordinates extraction and comparison
- Application data parsing (JSON, CSV, form input)
- Session and results persistence
- Stateless API design (all state in database) for horizontal scalability

### Label Extraction Pipeline
- **LLM with vision capabilities** (Claude or GPT-4o) for combined OCR + structured field extraction
  - Vision models can extract text and understand layout in a single call, potentially eliminating the need for a separate OCR service
  - Returns extracted field values with approximate bounding regions
- **Fallback/enhancement:** Dedicated OCR service (Azure Document Intelligence or Google Vision API) for precise bounding box coordinates if LLM-only coordinates are insufficient for annotation
- Field normalizer for unit/format standardization

### Comparison & Verification Engine
- Field-level matching with strategy dispatch (exact, fuzzy, numeric, presence)
- Compliance rule engine for mandatory field checks by beverage type
- Per-field and overall confidence scoring with configurable thresholds

### Label Annotation Engine
- Overlays bounding boxes on original label images (server-side or client-side canvas rendering)
- Color-coded by verification status (green/red/yellow)

### Database
- **SQLite** for the prototype (zero-configuration, file-based)
- Schema supports: verification sessions, label records, extracted data, comparison results, agent feedback, annotated image references
- Designed for straightforward migration to PostgreSQL for production

### Deployment
- Frontend: Vercel or Netlify (static SPA hosting)
- Backend: Railway, Render, or Fly.io (containerized API)
- Database: SQLite file on backend host (prototype); PostgreSQL for production
- Publicly accessible URL for evaluation
- Architecture compatible with future Azure/on-premise deployment

---

## 9. Scope & Prioritization

### Must Have (Prototype)
- Single-label upload with multi-image support (front/back/other drop zones)
- Application data input (manual form + JSON upload)
- LLM-based label extraction with field identification
- Field-by-field comparison table with match/mismatch/missing/uncertain status
- Complete field-to-strategy matching (fuzzy, numeric, exact, presence)
- Government warning statement exact verification against canonical text
- Annotated label output with color-coded bounding boxes
- Mandatory field checks by beverage type (spirits, wine, beer)
- Assist Mode with per-field agent override capability
- Basic review history (list, filter, drill into past verifications)

### Should Have
- Batch upload and processing with CSV mapping and progress tracking
- Confidence scoring per field with configurable thresholds
- Agent feedback loop (correct/incorrect marking with optional notes)
- Proof cross-validation (proof = ABV x 2)
- Image preprocessing for improved extraction on stylized/decorative labels

### Nice to Have
- QA sampling with blind review
- Accuracy dashboard with trend metrics
- Shadow Mode and Autonomous Mode
- Export verification report as PDF/JSON
- Photographic image handling (glare, rotation, poor lighting)

### Out of Scope (Future Production)
- COLA system integration
- Applicant notification workflows
- Multi-agent assignment and workload balancing
- Formal audit trail with regulatory compliance
- Approval/rejection workflow with digital signatures
- Model fine-tuning from labeled dataset

---

## 10. Assumptions & Resolved Questions

### Assumptions
- The prototype uses simulated application data (JSON/CSV) rather than live COLA data
- A cloud-hosted LLM API is acceptable for the prototype; production would need to evaluate on-premise options
- Agents using the prototype will have modern web browsers (Chrome, Edge)
- The primary input is submitted label artwork (flat design files), not photographs of bottles
- All three beverage types (beer, wine, distilled spirits) are in scope for the prototype

### Resolved from Draft v1
- **Government warning canonical text** -- Included in Section 5.3.3
- **Fields mandatory by beverage type** -- Defined in Section 5.3.4
- **Warning requirements by beverage type** -- The same warning text is required on all alcohol beverages regardless of type or container size
- **PDF/scan support** -- Yes, PDF is an accepted input format (label artwork is sometimes submitted as PDF)

### Remaining Open Questions
- For batch processing, should the CSV schema match a specific COLA export format, or is a generic schema sufficient for the prototype?
- What is the acceptable false negative rate before agents lose trust in the tool? (Recommendation: track during Assist Mode and let agent feedback data answer this empirically)
- Are there additional wine-specific fields (varietal, vintage, appellation details) that should be extracted beyond what is listed?

---

## 11. Test Data Reference

The prototype includes a curated test dataset organized by expected verification outcome:

| Folder | Count | Purpose |
|--------|-------|---------|
| `good spirits` | 18 images | Compliant spirits labels -- all required fields present and correct |
| `good wine+beer` | 5 images | Compliant wine/beer labels -- baseline passing cases |
| `bad spirits label` | 18 images | Spirits labels with content issues (missing fields, non-English text, incorrect values) |
| `bad spirits photo` | 23 images | Spirits labels with extraction challenges (stylized fonts, decorative designs, low contrast) |
| `bad spirits warning` | 20 images | Spirits labels with missing or incorrect government warning statement |
| `bad wine+beer` | 5 images | Wine/beer labels with compliance issues |

**Total: 89 test images** across 6 categories.

Test data consists of flat label artwork files (not photographs). Each label may have multiple image files (front, back, other) identified by filename suffix. Corresponding application data (JSON/CSV) will be created to pair with these images for automated testing.

---

## 12. Phased Rollout Plan

### Phase 1: Prototype Delivery
Deploy working prototype with Assist Mode. Verify against test dataset. Ensure all Must Have features are functional and performant.

### Phase 2: Stakeholder Evaluation
Sarah, Dave, and Jenny test the prototype against real-world label samples. Collect feedback on accuracy, usability, and trust. Iterate on extraction and matching based on findings.

### Phase 3: Shadow Mode Pilot (Future)
AI runs on real label submissions in the background. Results compared to agent decisions. No agent workflow disruption. Accuracy metrics collected over 2-4 weeks.

### Phase 4: Expanded Assist Mode (Future)
Roll out to full agent team. Batch processing enabled. QA sampling begins. Confidence thresholds calibrated based on accumulated data.

### Phase 5: Autonomous Mode Evaluation (Future)
Leadership reviews accuracy data and agent feedback. If thresholds are met, enable Autonomous Mode for high-confidence verifications. Human review continues for flagged items.

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM extraction inaccuracy on stylized/decorative labels | False mismatches erode agent trust | Confidence scoring + "Extraction Uncertain" status for low-confidence fields; separate failure category so agents understand why |
| Processing time exceeds 5-second threshold | Agents abandon tool (repeat of vendor pilot) | LLM vision for single-call extraction (fewer round trips than OCR+LLM pipeline); async processing for batch; performance monitoring and optimization |
| Government warning false positives (cosmetic formatting flagged as errors) | Agent frustration, override fatigue | Whitespace/line-break normalization before exact match; only enforce wording and capitalization, not visual formatting |
| Agent resistance to adoption | Low utilization despite investment | Assist Mode preserves agent authority; involve agents (Dave, Jenny) in testing and feedback; demonstrate time savings on routine labels |
| Network/firewall blocks AI API calls in production | Core functionality unavailable on government network | Document all API dependencies; architect for future on-premise deployment; evaluate self-hosted model options for production |
| Bounding box coordinates from LLM are imprecise | Annotation overlay misaligns with label fields | Fallback to dedicated OCR service for coordinate extraction; provide manual adjustment capability for agents |
| Scope creep during prototype development | Incomplete core features | Strict Must Have / Should Have prioritization; working core over ambitious extras; "a working core application with clean code is preferred over ambitious but incomplete features" |
| Multi-image merging produces duplicate/conflicting field values | Confusing results when front and back labels both contain a field | Merge strategy: prefer front label values; flag conflicts as "Needs Review" with both values shown |
