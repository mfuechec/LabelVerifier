import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)

from app.api.dependencies import get_db, get_db_path
from app.config import settings
from app.models.schemas import ApplicationData, BatchResponse, BatchSessionItem, BatchStatus
from app.services.orchestrator import VerificationOrchestrator
from app.services.pdf_parser import PDFApplicationParser

router = APIRouter()


def _assign_panels(count: int) -> list[str]:
    """Assign panel names: front, back, then other_N for additional images."""
    if count == 0:
        return []
    names = ["front"]
    if count >= 2:
        names.append("back")
    for i in range(2, count):
        names.append(f"other_{i - 1}")
    return names

_pdf_parser = PDFApplicationParser()


def get_orchestrator(request: Request | None = None) -> VerificationOrchestrator:
    db_path = get_db_path(request)
    return VerificationOrchestrator(db_path=db_path)


@router.post("/batch")
async def create_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    application_pdfs: list[UploadFile] = File(..., alias="application_pdfs[]"),
    images: list[UploadFile] = File(..., alias="images[]"),
    image_assignments: list[str] = Form(..., alias="image_assignments[]"),
):
    if not application_pdfs:
        raise HTTPException(status_code=422, detail="At least one application PDF is required")

    if len(image_assignments) != len(application_pdfs):
        raise HTTPException(
            status_code=422,
            detail=f"Number of image assignments ({len(image_assignments)}) must match number of PDFs ({len(application_pdfs)})",
        )

    # Parse assignments JSON
    parsed_assignments: list[list[int]] = []
    for assignment_str in image_assignments:
        try:
            indices = json.loads(assignment_str)
            if not isinstance(indices, list):
                raise ValueError
            parsed_assignments.append(indices)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid image_assignments format; each entry must be a JSON array of image indices")

    # Read all image bytes upfront
    image_bytes_list: list[bytes] = []
    for img in images:
        content = await img.read()
        if img.content_type and img.content_type not in settings.allowed_mime_types:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported image type: {img.content_type}",
            )
        if len(content) > settings.max_image_size:
            raise HTTPException(
                status_code=422,
                detail=f"Image too large: {len(content)} bytes. Maximum: {settings.max_image_size}",
            )
        image_bytes_list.append(content)

    # Parse each PDF
    app_data_list: list[ApplicationData] = []
    for pdf_file in application_pdfs:
        pdf_bytes = await pdf_file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=422, detail="Application PDF is empty")
        try:
            app_data = _pdf_parser.parse_application_pdf(pdf_bytes)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        app_data_list.append(app_data)

    # Create batch record
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    total_items = len(application_pdfs)

    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        conn.execute(
            """INSERT INTO batches (id, status, total_items, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (batch_id, "processing", total_items, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    # Build item list for parallel processing
    batch_items = []
    for i, app_data in enumerate(app_data_list):
        assigned_indices = parsed_assignments[i]
        item_images = [image_bytes_list[idx] for idx in assigned_indices]
        panels = _assign_panels(len(item_images))
        batch_items.append((app_data, item_images, panels))

    # Single background task that processes all items in parallel
    background_tasks.add_task(
        _process_batch,
        db_path=db_path,
        batch_id=batch_id,
        items=batch_items,
    )

    return {"data": {"batch_id": batch_id, "total_items": total_items}}


@router.get("/batch/{batch_id}")
def get_batch(batch_id: str, request: Request):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Batch not found")

        batch = BatchStatus(
            batch_id=row["id"],
            status=row["status"],
            total_items=row["total_items"],
            completed_items=row["completed_items"],
            failed_items=row["failed_items"],
            created_at=row["created_at"],
        )

        # Get sessions belonging to this batch
        sessions = conn.execute(
            """SELECT vs.id, vs.beverage_type, vs.status, vs.overall_confidence, vs.created_at,
                      a.brand_name
               FROM verification_sessions vs
               LEFT JOIN applications a ON a.session_id = vs.id
               WHERE vs.batch_id = ?
               ORDER BY vs.created_at""",
            (batch_id,),
        ).fetchall()

        items = [
            BatchSessionItem(
                session_id=s["id"],
                brand_name=s["brand_name"],
                beverage_type=s["beverage_type"],
                status=s["status"],
                overall_confidence=s["overall_confidence"],
                created_at=s["created_at"],
            )
            for s in sessions
        ]

        return {"data": BatchResponse(batch=batch, items=items).model_dump()}
    finally:
        conn.close()


async def _process_batch(
    db_path: str,
    batch_id: str,
    items: list[tuple[ApplicationData, list[bytes], list[str]]],
):
    """Process all batch items in parallel using asyncio.gather."""
    tasks = [
        _process_single_item(db_path, batch_id, app_data, images, panels)
        for app_data, images, panels in items
    ]
    await asyncio.gather(*tasks)

    # Mark batch as completed or failed
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db(db_path)
    try:
        row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if row:
            new_status = "failed" if row["failed_items"] == row["total_items"] else "completed"
            conn.execute(
                "UPDATE batches SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, batch_id),
            )
            conn.commit()
    finally:
        conn.close()


async def _process_single_item(
    db_path: str,
    batch_id: str,
    app_data: ApplicationData,
    images: list[bytes],
    panels: list[str],
):
    orchestrator = VerificationOrchestrator(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()

    try:
        logger.info("Batch %s: processing item for %s (%d images)", batch_id, app_data.brand_name, len(images))
        result = await orchestrator.verify_single(images, panels, app_data, batch_id=batch_id)
        logger.info("Batch %s: item completed, status=%s confidence=%.1f", batch_id, result.status, result.overall_confidence)

        conn = get_db(db_path)
        try:
            conn.execute(
                """UPDATE batches SET completed_items = completed_items + 1, updated_at = ?
                   WHERE id = ?""",
                (now, batch_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("Batch %s: item failed: %s", batch_id, exc)
        conn = get_db(db_path)
        try:
            conn.execute(
                """UPDATE batches SET failed_items = failed_items + 1, updated_at = ?
                   WHERE id = ?""",
                (now, batch_id),
            )
            conn.commit()
        finally:
            conn.close()
