import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import OverrideRequest, DecisionRequest, FeedbackRequest
from app.db.setup import get_db

router = APIRouter()


def get_db_path(request: Request | None = None) -> str:
    if request and hasattr(request.app.state, "db_path"):
        return request.app.state.db_path
    return "data/labelverify.db"


@router.patch("/verify/{session_id}/fields/{field_name}")
async def override_field(
    session_id: str,
    field_name: str,
    body: OverrideRequest,
    request: Request,
):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        conn.execute(
            """UPDATE comparison_results
               SET override_status = ?, override_note = ?
               WHERE session_id = ? AND field_name = ?""",
            (body.override_status, body.note, session_id, field_name),
        )
        conn.commit()
        return {"data": {"status": "updated"}}
    finally:
        conn.close()


@router.post("/verify/{session_id}/decision")
async def submit_decision(
    session_id: str,
    body: DecisionRequest,
    request: Request,
):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE verification_sessions
               SET agent_decision = ?, agent_notes = ?, updated_at = ?
               WHERE id = ?""",
            (body.decision, body.notes, now, session_id),
        )
        conn.commit()
        return {"data": {"status": "updated"}}
    finally:
        conn.close()


@router.post("/verify/{session_id}/feedback")
async def submit_feedback(
    session_id: str,
    body: FeedbackRequest,
    request: Request,
):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        now = datetime.now(timezone.utc).isoformat()
        feedback_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO agent_feedback
               (id, session_id, ai_correct, field_name, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (feedback_id, session_id, 1 if body.ai_correct else 0,
             body.field_name, body.note, now),
        )

        conn.execute(
            """UPDATE verification_sessions
               SET ai_correct = ?, updated_at = ?
               WHERE id = ?""",
            (1 if body.ai_correct else 0, now, session_id),
        )
        conn.commit()
        return {"data": {"status": "recorded"}}
    finally:
        conn.close()
