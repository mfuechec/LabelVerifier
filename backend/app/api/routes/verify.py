from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Request
from app.models.schemas import VerificationResult
from app.services.orchestrator import VerificationOrchestrator
from app.services.pdf_parser import PDFApplicationParser
from app.config import settings
from app.api.dependencies import get_db, get_db_path

router = APIRouter()

_pdf_parser = PDFApplicationParser()


def get_orchestrator(request: Request | None = None) -> VerificationOrchestrator:
    db_path = get_db_path(request)
    return VerificationOrchestrator(db_path=db_path)


@router.post("/verify")
async def verify_label(
    request: Request,
    application_pdf: UploadFile = File(..., alias="application_pdf"),
    images: list[UploadFile] = File(..., alias="images[]"),
    panels: list[str] = Form(None, alias="panels[]"),
):
    # Parse application data from PDF
    pdf_bytes = await application_pdf.read()
    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="Application PDF is empty")

    if application_pdf.content_type and application_pdf.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail=f"Application file must be a PDF, got: {application_pdf.content_type}",
        )

    try:
        app_data = _pdf_parser.parse_application_pdf(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not images:
        raise HTTPException(status_code=422, detail="At least one image is required")

    # Default panels if not provided
    if not panels:
        panels = ["front"] + ["other"] * (len(images) - 1)

    # Read image bytes
    image_bytes = []
    for img in images:
        content = await img.read()
        if img.content_type not in settings.allowed_mime_types:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {img.content_type}. Allowed: {', '.join(settings.allowed_mime_types)}",
            )
        if len(content) > settings.max_image_size:
            raise HTTPException(
                status_code=422,
                detail=f"Image too large: {len(content)} bytes. Maximum: {settings.max_image_size} bytes",
            )
        image_bytes.append(content)

    orchestrator = get_orchestrator(request)
    result = await orchestrator.verify_single(image_bytes, panels, app_data)

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

        field_results = [
            {
                "field_name": f["field_name"],
                "declared_value": f["declared_value"],
                "extracted_value": f["extracted_value"],
                "status": f["status"],
                "confidence": f["confidence"],
                "match_strategy": f["match_strategy"],
                "bounding_box": None,
            }
            for f in fields
        ]

        return {
            "data": {
                "session_id": row["id"],
                "status": row["status"],
                "overall_confidence": row["overall_confidence"],
                "beverage_type": row["beverage_type"],
                "fields": field_results,
                "annotated_images": {},
                "created_at": row["created_at"],
            }
        }
    finally:
        conn.close()
