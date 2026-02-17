from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import OverrideRequest, DecisionRequest, FeedbackRequest
from app.api.dependencies import get_repo

router = APIRouter()


@router.patch("/verify/{session_id}/fields/{field_name}")
def override_field(
    session_id: str,
    field_name: str,
    body: OverrideRequest,
    request: Request,
):
    repo = get_repo(request)
    if not repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    repo.override_field(session_id, field_name, body.override_status, body.note)
    return {"data": {"status": "updated"}}


@router.post("/verify/{session_id}/decision")
def submit_decision(
    session_id: str,
    body: DecisionRequest,
    request: Request,
):
    repo = get_repo(request)
    if not repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    repo.update_decision(session_id, body.decision, body.notes)
    return {"data": {"status": "updated"}}


@router.post("/verify/{session_id}/feedback")
def submit_feedback(
    session_id: str,
    body: FeedbackRequest,
    request: Request,
):
    repo = get_repo(request)
    if not repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    repo.update_feedback(session_id, body.ai_correct, body.field_name, body.note)
    return {"data": {"status": "recorded"}}
