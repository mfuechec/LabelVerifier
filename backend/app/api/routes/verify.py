import os
import re

from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from app.models.schemas import VerificationResult
from app.services.orchestrator import IMAGES_BASE_DIR
from app.services.pdf_parser import COLAPDFParser
from app.api.dependencies import get_db, get_db_path, get_orchestrator

router = APIRouter()

_pdf_parser = COLAPDFParser()

# Valid panel names (prevents path traversal in panel parameter)
VALID_PANELS = {"front", "back", "other"}
# Regex for batch upload panel names: label_1, label_2, etc.
_LABEL_PANEL_RE = re.compile(r'^label_\d+$')


@router.post("/verify")
async def verify_label(
    request: Request,
    cola_pdf: UploadFile = File(...),
):
    """Verify a label from a COLA PDF (TTB F 5100.31).

    The PDF contains both the application form (page 1) and label images (pages 2+).
    """
    pdf_bytes = await cola_pdf.read()
    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="COLA PDF is empty")

    if cola_pdf.content_type and cola_pdf.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail=f"File must be a PDF, got: {cola_pdf.content_type}",
        )

    try:
        parse_result = _pdf_parser.parse(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not parse_result.label_images:
        raise HTTPException(
            status_code=422,
            detail="No label images found in PDF. The PDF may be incomplete.",
        )

    orchestrator = get_orchestrator(request)
    result = await orchestrator.verify_from_cola(parse_result)

    return {"data": result.model_dump()}


@router.get("/verify/{session_id}")
def get_verification(session_id: str, request: Request):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Verification session not found")

        # Get comparison results
        fields = conn.execute(
            "SELECT * FROM comparison_results WHERE session_id = ?", (session_id,)
        ).fetchall()

        field_results = []
        flagged_fields = []
        reviewed_count = 0
        for f in fields:
            is_reviewed = bool(f["reviewed"]) or f["override_status"] is not None
            if is_reviewed:
                reviewed_count += 1
            status = f["status"]
            if status == "extraction_uncertain":
                flagged_fields.append(f["field_name"])
            field_results.append({
                "field_name": f["field_name"],
                "declared_value": f["declared_value"],
                "extracted_value": f["extracted_value"],
                "status": status,
                "confidence": f["confidence"],
                "match_strategy": f["match_strategy"],
                "bounding_box": None,
                "extraction_confidence": f["extraction_confidence"],
                "confidence_reason": f["confidence_reason"],
                "reviewed": is_reviewed,
            })

        review_summary = {
            "total_fields": len(field_results),
            "fields_needing_review": len(flagged_fields),
            "fields_reviewed": reviewed_count,
            "flagged_field_names": flagged_fields,
        }

        # Build annotated_images from stored files
        annotated_images = {}
        img_dir = os.path.join(IMAGES_BASE_DIR, session_id)
        if os.path.isdir(img_dir):
            for fname in os.listdir(img_dir):
                panel_name = os.path.splitext(fname)[0]
                annotated_images[panel_name] = f"/api/v1/images/{session_id}/{panel_name}"

        # Build processing stats if available
        processing_stats = None
        try:
            if row["total_llm_calls"]:
                processing_stats = {
                    "total_llm_calls": row["total_llm_calls"],
                    "total_input_tokens": row["total_input_tokens"],
                    "total_output_tokens": row["total_output_tokens"],
                    "extraction_time_ms": row["extraction_time_ms"] or 0,
                    "total_time_ms": row["processing_time_ms"],
                }
        except (IndexError, KeyError):
            pass

        return {
            "data": {
                "session_id": row["id"],
                "status": row["status"],
                "overall_confidence": row["overall_confidence"],
                "beverage_type": row["beverage_type"],
                "fields": field_results,
                "annotated_images": annotated_images,
                "created_at": row["created_at"],
                "review_summary": review_summary,
                "processing_stats": processing_stats,
            }
        }
    finally:
        conn.close()


@router.post("/verify/{session_id}/fields/{field_name}/review")
def review_field(session_id: str, field_name: str, request: Request):
    """Mark a field as reviewed without changing its status."""
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        # Verify session exists
        session = conn.execute(
            "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Verification session not found")

        # Verify field exists
        field = conn.execute(
            "SELECT id FROM comparison_results WHERE session_id = ? AND field_name = ?",
            (session_id, field_name),
        ).fetchone()
        if not field:
            raise HTTPException(status_code=404, detail=f"Field '{field_name}' not found")

        conn.execute(
            "UPDATE comparison_results SET reviewed = 1 WHERE session_id = ? AND field_name = ?",
            (session_id, field_name),
        )
        conn.commit()

        return {"reviewed": True, "field_name": field_name}
    finally:
        conn.close()


@router.get("/images/{session_id}/{panel}")
def serve_image(session_id: str, panel: str, request: Request):
    """Serve a stored label image."""
    # Validate session_id format (UUID only -- prevent path traversal)
    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    # Validate panel name (front/back/other for single upload, label_N for batch)
    if panel not in VALID_PANELS and not _LABEL_PANEL_RE.match(panel):
        raise HTTPException(status_code=400, detail=f"Invalid panel: {panel}")

    # Verify session exists in DB
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        session = conn.execute(
            "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Verification session not found")
    finally:
        conn.close()

    # Serve the file
    image_path = os.path.join(IMAGES_BASE_DIR, session_id, f"{panel}.jpg")
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path, media_type="image/jpeg")
