"""Database helper functions for CRUD operations."""
from app.db.setup import get_db


def get_session(db_path: str, session_id: str) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM verification_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_sessions(
    db_path: str,
    status: str | None = None,
    beverage_type: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    conn = get_db(db_path)
    try:
        where = []
        params: list = []
        if status:
            where.append("status = ?")
            params.append(status)
        if beverage_type:
            where.append("beverage_type = ?")
            params.append(beverage_type)

        where_sql = " AND ".join(where)
        if where_sql:
            where_sql = "WHERE " + where_sql

        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM verification_sessions {where_sql}", params
        ).fetchone()["cnt"]

        rows = conn.execute(
            f"SELECT * FROM verification_sessions {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [per_page, (page - 1) * per_page],
        ).fetchall()

        return [dict(r) for r in rows], total
    finally:
        conn.close()


def update_field_override(
    db_path: str, session_id: str, field_name: str, status: str, note: str | None
) -> bool:
    conn = get_db(db_path)
    try:
        result = conn.execute(
            """UPDATE comparison_results SET override_status = ?, override_note = ?
               WHERE session_id = ? AND field_name = ?""",
            (status, note, session_id, field_name),
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()
