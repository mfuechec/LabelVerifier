import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)

from app.api.dependencies import get_db, get_db_path
from app.models.schemas import BatchResponse, BatchSessionItem, BatchStatus
from app.services.orchestrator import VerificationOrchestrator
from app.services.pdf_parser import COLAPDFParser, COLAParseResult

router = APIRouter()

_pdf_parser = COLAPDFParser()


@router.post("/batch")
async def create_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    cola_pdfs: list[UploadFile] = File(..., alias="cola_pdfs[]"),
):
    """Submit multiple COLA PDFs for batch verification.

    Each PDF is self-contained (application form + label images).
    """
    if not cola_pdfs:
        raise HTTPException(status_code=422, detail="At least one COLA PDF is required")

    # Parse each PDF upfront to fail fast on bad inputs
    parse_results: list[COLAParseResult] = []
    for pdf_file in cola_pdfs:
        pdf_bytes = await pdf_file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=422, detail="COLA PDF is empty")
        if pdf_file.content_type and pdf_file.content_type != "application/pdf":
            raise HTTPException(
                status_code=422,
                detail=f"File must be a PDF, got: {pdf_file.content_type}",
            )
        try:
            result = _pdf_parser.parse(pdf_bytes)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not result.label_images:
            brand = result.application_data.brand_name or "unknown"
            raise HTTPException(
                status_code=422,
                detail=f"No label images found in PDF for '{brand}'",
            )
        parse_results.append(result)

    # Create batch record
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    total_items = len(parse_results)

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

    background_tasks.add_task(
        _process_batch,
        db_path=db_path,
        batch_id=batch_id,
        parse_results=parse_results,
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
    parse_results: list[COLAParseResult],
):
    """Process all batch items in parallel."""
    tasks = [
        _process_single_item(db_path, batch_id, pr)
        for pr in parse_results
    ]
    await asyncio.gather(*tasks)

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
    parse_result: COLAParseResult,
):
    orchestrator = VerificationOrchestrator(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()

    try:
        brand = parse_result.application_data.brand_name
        n_imgs = len(parse_result.label_images)
        logger.info("Batch %s: processing %s (%d images)", batch_id, brand, n_imgs)
        result = await orchestrator.verify_from_cola(parse_result, batch_id=batch_id)
        logger.info("Batch %s: %s completed, status=%s", batch_id, brand, result.status)

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
