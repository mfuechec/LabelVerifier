"""Repository layer: all SQL lives here."""

import uuid
from datetime import datetime, timezone

from app.db.setup import get_db
from app.models.schemas import (
    ApplicationData,
    FieldComparisonResult,
    ProcessingStats,
)


class VerificationRepository:
    def __init__(self, db_path: str = "data/labelverify.db"):
        self.db_path = db_path

    def _conn(self):
        return get_db(self.db_path)

    # ── Session operations ──────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        app_data: ApplicationData,
        fields: list[FieldComparisonResult],
        confidence: float,
        status: str,
        now: str,
        batch_id: str | None = None,
        processing_stats: ProcessingStats | None = None,
    ):
        """Persist a complete verification session (session + application + comparison results)."""
        conn = self._conn()
        try:
            with conn:
                ps = processing_stats or ProcessingStats()
                conn.execute(
                    """INSERT INTO verification_sessions
                       (id, application_id, beverage_type, status,
                        overall_confidence, batch_id,
                        total_input_tokens, total_output_tokens,
                        total_llm_calls, processing_time_ms, extraction_time_ms,
                        estimated_cost_usd, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, app_data.application_id,
                     app_data.beverage_type, status, confidence, batch_id,
                     ps.total_input_tokens, ps.total_output_tokens,
                     ps.total_llm_calls, ps.total_time_ms, ps.extraction_time_ms,
                     ps.estimated_cost_usd, now, now),
                )

                app_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO applications
                       (id, session_id, brand_name, class_type, alcohol_content,
                        net_contents, producer_name, producer_address,
                        country_of_origin, importer_name, importer_address,
                        has_sulfites_declaration, raw_json,
                        fanciful_name, ttb_id, source_of_product)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (app_id, session_id, app_data.brand_name, app_data.class_type,
                     app_data.alcohol_content, app_data.net_contents,
                     app_data.producer_name, app_data.producer_address,
                     app_data.country_of_origin, app_data.importer_name,
                     app_data.importer_address,
                     1 if app_data.has_sulfites_declaration else 0,
                     app_data.model_dump_json(),
                     app_data.fanciful_name, app_data.ttb_id,
                     app_data.source_of_product),
                )

                for field in fields:
                    cr_id = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO comparison_results
                           (id, session_id, field_name, declared_value,
                            extracted_value, match_strategy, status, confidence,
                            extraction_confidence, confidence_reason)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (cr_id, session_id, field.field_name,
                         field.declared_value, field.extracted_value,
                         field.match_strategy, field.status, field.confidence,
                         field.extraction_confidence, field.confidence_reason),
                    )
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict | None:
        """Get a verification session by ID. Returns dict or None."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM verification_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_session_fields(self, session_id: str) -> list[dict]:
        """Get all comparison results for a session."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM comparison_results WHERE session_id = ?", (session_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_decision(self, session_id: str, decision: str, notes: str | None):
        """Record agent decision on a session."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE verification_sessions
                   SET agent_decision = ?, agent_notes = ?, updated_at = ?
                   WHERE id = ?""",
                (decision, notes, now, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_feedback(self, session_id: str, ai_correct: bool, field_name: str | None, note: str | None):
        """Record agent feedback on a session."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            feedback_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO agent_feedback
                   (id, session_id, ai_correct, field_name, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (feedback_id, session_id, 1 if ai_correct else 0,
                 field_name, note, now),
            )
            conn.execute(
                """UPDATE verification_sessions
                   SET ai_correct = ?, updated_at = ?
                   WHERE id = ?""",
                (1 if ai_correct else 0, now, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Field operations ────────────────────────────────────────────

    def override_field(self, session_id: str, field_name: str, override_status: str, note: str | None):
        """Override a field's status."""
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE comparison_results
                   SET override_status = ?, override_note = ?
                   WHERE session_id = ? AND field_name = ?""",
                (override_status, note, session_id, field_name),
            )
            conn.commit()
        finally:
            conn.close()

    def review_field(self, session_id: str, field_name: str) -> bool:
        """Mark a field as reviewed. Returns True if the field exists."""
        conn = self._conn()
        try:
            field = conn.execute(
                "SELECT id FROM comparison_results WHERE session_id = ? AND field_name = ?",
                (session_id, field_name),
            ).fetchone()
            if not field:
                return False
            conn.execute(
                "UPDATE comparison_results SET reviewed = 1 WHERE session_id = ? AND field_name = ?",
                (session_id, field_name),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # ── History / listing ───────────────────────────────────────────

    def list_verifications(
        self,
        status: str | None = None,
        beverage_type: str | None = None,
        brand: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """List verification sessions with optional filters. Returns (items, total)."""
        where_clauses = []
        params: list = []

        if status:
            where_clauses.append("vs.status = ?")
            params.append(status)
        if beverage_type:
            where_clauses.append("vs.beverage_type = ?")
            params.append(beverage_type)
        if brand:
            where_clauses.append("a.brand_name LIKE ?")
            params.append(f"%{brand}%")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = self._conn()
        try:
            total = conn.execute(
                f"""SELECT COUNT(*) as cnt
                    FROM verification_sessions vs
                    LEFT JOIN applications a ON a.session_id = vs.id
                    {where_sql}""",
                params,
            ).fetchone()["cnt"]

            offset = (page - 1) * per_page
            rows = conn.execute(
                f"""SELECT vs.id as session_id, vs.application_id, a.brand_name,
                           vs.beverage_type, vs.status, vs.overall_confidence,
                           vs.agent_decision, vs.created_at,
                           vs.processing_time_ms, vs.total_input_tokens,
                           vs.total_output_tokens, vs.estimated_cost_usd
                    FROM verification_sessions vs
                    LEFT JOIN applications a ON a.session_id = vs.id
                    {where_sql}
                    ORDER BY vs.created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [per_page, offset],
            ).fetchall()

            items = [
                {
                    "session_id": r["session_id"],
                    "application_id": r["application_id"],
                    "brand_name": r["brand_name"],
                    "beverage_type": r["beverage_type"],
                    "status": r["status"],
                    "overall_confidence": r["overall_confidence"],
                    "agent_decision": r["agent_decision"],
                    "created_at": r["created_at"],
                    "processing_time_ms": r["processing_time_ms"],
                    "total_tokens": (r["total_input_tokens"] or 0) + (r["total_output_tokens"] or 0),
                    "estimated_cost_usd": r["estimated_cost_usd"],
                }
                for r in rows
            ]
            return items, total
        finally:
            conn.close()

    # ── Batch operations ────────────────────────────────────────────

    def create_batch(self, batch_id: str, total_items: int, skipped: list[tuple[str, str]]):
        """Create a batch record with skipped items."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO batches (id, status, total_items, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (batch_id, "processing", total_items, now, now),
            )
            for filename, reason in skipped:
                conn.execute(
                    """INSERT INTO batch_skipped_items (id, batch_id, filename, reason)
                       VALUES (?, ?, ?, ?)""",
                    (str(uuid.uuid4()), batch_id, filename, reason),
                )
            conn.commit()
        finally:
            conn.close()

    def get_batch(self, batch_id: str) -> dict | None:
        """Get a batch record by ID."""
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_batch_sessions(self, batch_id: str) -> list[dict]:
        """Get all sessions for a batch."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT vs.id, vs.beverage_type, vs.status, vs.overall_confidence, vs.created_at,
                          vs.total_input_tokens, vs.total_output_tokens,
                          vs.total_llm_calls, vs.processing_time_ms, vs.extraction_time_ms,
                          a.brand_name
                   FROM verification_sessions vs
                   LEFT JOIN applications a ON a.session_id = vs.id
                   WHERE vs.batch_id = ?
                   ORDER BY vs.created_at""",
                (batch_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_batch_skipped(self, batch_id: str) -> list[dict]:
        """Get skipped items for a batch."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT filename, reason FROM batch_skipped_items WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def increment_batch_completed(self, batch_id: str):
        """Increment completed_items counter for a batch."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE batches SET completed_items = completed_items + 1, updated_at = ?
                   WHERE id = ?""",
                (now, batch_id),
            )
            conn.commit()
        finally:
            conn.close()

    def increment_batch_failed(self, batch_id: str):
        """Increment failed_items counter for a batch."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE batches SET failed_items = failed_items + 1, updated_at = ?
                   WHERE id = ?""",
                (now, batch_id),
            )
            conn.commit()
        finally:
            conn.close()

    def finalize_batch(self, batch_id: str):
        """Mark batch as completed or failed based on item counts."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
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

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT id FROM verification_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
