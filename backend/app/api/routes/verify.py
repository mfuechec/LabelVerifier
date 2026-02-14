import json
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Request
from app.models.schemas import ApplicationData, VerificationResult
from app.services.orchestrator import VerificationOrchestrator
from app.db.setup import get_db

router = APIRouter()


def get_db_path(request: Request | None = None) -> str:
    """Get DB path from app state or default."""
    if request and hasattr(request.app.state, "db_path"):
        return request.app.state.db_path
    return "data/labelverify.db"


def get_orchestrator(request: Request | None = None) -> VerificationOrchestrator:
    db_path = get_db_path(request)
    return VerificationOrchestrator(db_path=db_path)


@router.post("/verify")
async def verify_label(
    request: Request,
    application_data: str = Form(...),
    images: list[UploadFile] = File(..., alias="images[]"),
    panels: list[str] = Form(None, alias="panels[]"),
):
    # Parse application data
    try:
        app_data_dict = json.loads(application_data)
        app_data = ApplicationData(**app_data_dict)
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(status_code=422, detail=f"Invalid application data: {str(e)}")

    if not images:
        raise HTTPException(status_code=422, detail="At least one image is required")

    # Default panels if not provided
    if not panels:
        panels = ["front"] + ["other"] * (len(images) - 1)

    # Read image bytes
    image_bytes = []
    for img in images:
        content = await img.read()
        image_bytes.append(content)

    orchestrator = get_orchestrator(request)
    result = await orchestrator.verify_single(image_bytes, panels, app_data)

    return {"data": result.model_dump()}


@router.get("/verify/{session_id}")
async def get_verification(session_id: str, request: Request):
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
