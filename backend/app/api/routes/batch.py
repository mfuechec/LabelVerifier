import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)

from app.api.dependencies import get_db_path, get_repo
from app.db.repository import VerificationRepository
from app.models.schemas import BatchResponse, BatchSessionItem, BatchSkippedItem, BatchStatus, ProcessingStats
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

    # Parse each PDF, collecting valid results and skipped items
    parse_results: list[COLAParseResult] = []
    skipped: list[tuple[str, str]] = []  # (filename, reason)

    for pdf_file in cola_pdfs:
        filename = pdf_file.filename or "unknown"
        pdf_bytes = await pdf_file.read()

        if not pdf_bytes:
            skipped.append((filename, "Empty file"))
            continue

        if pdf_file.content_type and pdf_file.content_type != "application/pdf":
            skipped.append((filename, f"Not a PDF (got {pdf_file.content_type})"))
            continue

        try:
            result = _pdf_parser.parse(pdf_bytes)
        except ValueError as e:
            skipped.append((filename, str(e)))
            continue

        if not result.label_images:
            brand = result.application_data.brand_name or "unknown"
            skipped.append((filename, f"No label images found in PDF for '{brand}'"))
            continue

        parse_results.append(result)

    if not parse_results:
        raise HTTPException(
            status_code=422,
            detail=f"No valid COLA PDFs to process ({len(skipped)} skipped)",
        )

    batch_id = str(uuid.uuid4())
    total_items = len(parse_results)

    db_path = get_db_path(request)
    repo = get_repo(request)
    repo.create_batch(batch_id, total_items, skipped)

    background_tasks.add_task(
        _process_batch,
        db_path=db_path,
        batch_id=batch_id,
        parse_results=parse_results,
    )

    return {
        "data": {
            "batch_id": batch_id,
            "total_items": total_items,
            "skipped_count": len(skipped),
        }
    }


@router.get("/batch/{batch_id}")
def get_batch(batch_id: str, request: Request):
    repo = get_repo(request)
    batch = repo.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch_status = BatchStatus(
        batch_id=batch["id"],
        status=batch["status"],
        total_items=batch["total_items"],
        completed_items=batch["completed_items"],
        failed_items=batch["failed_items"],
        created_at=batch["created_at"],
    )

    sessions = repo.get_batch_sessions(batch_id)
    items = []
    for s in sessions:
        ps = None
        try:
            if s["total_llm_calls"]:
                ps = ProcessingStats(
                    total_llm_calls=s["total_llm_calls"],
                    total_input_tokens=s["total_input_tokens"],
                    total_output_tokens=s["total_output_tokens"],
                    extraction_time_ms=s["extraction_time_ms"] or 0,
                    total_time_ms=s["processing_time_ms"],
                )
        except (IndexError, KeyError):
            pass
        items.append(
            BatchSessionItem(
                session_id=s["id"],
                brand_name=s["brand_name"],
                beverage_type=s["beverage_type"],
                status=s["status"],
                overall_confidence=s["overall_confidence"],
                created_at=s["created_at"],
                processing_stats=ps,
            )
        )

    skipped_rows = repo.get_batch_skipped(batch_id)
    skipped_items = [
        BatchSkippedItem(filename=r["filename"], reason=r["reason"])
        for r in skipped_rows
    ]

    return {"data": BatchResponse(batch=batch_status, items=items, skipped_items=skipped_items).model_dump()}


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

    repo = VerificationRepository(db_path)
    repo.finalize_batch(batch_id)


async def _process_single_item(
    db_path: str,
    batch_id: str,
    parse_result: COLAParseResult,
):
    orchestrator = VerificationOrchestrator(db_path=db_path)
    repo = VerificationRepository(db_path)

    try:
        brand = parse_result.application_data.brand_name
        n_imgs = len(parse_result.label_images)
        logger.info("Batch %s: processing %s (%d images)", batch_id, brand, n_imgs)
        result = await orchestrator.verify_from_cola(parse_result, batch_id=batch_id)
        logger.info("Batch %s: %s completed, status=%s", batch_id, brand, result.status)
        repo.increment_batch_completed(batch_id)
    except Exception as exc:
        logger.exception("Batch %s: item failed: %s", batch_id, exc)
        repo.increment_batch_failed(batch_id)
