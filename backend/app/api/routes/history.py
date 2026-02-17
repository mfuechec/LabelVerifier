from fastapi import APIRouter, Query, Request
from app.api.dependencies import get_db, get_db_path

router = APIRouter()


@router.get("/verifications")
def list_verifications(
    request: Request,
    status: str | None = None,
    beverage_type: str | None = None,
    brand: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    db_path = get_db_path(request)
    conn = get_db(db_path)
    try:
        where_clauses = []
        params = []

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

        # Count total
        count_sql = f"""
            SELECT COUNT(*) as cnt
            FROM verification_sessions vs
            LEFT JOIN applications a ON a.session_id = vs.id
            {where_sql}
        """
        total = conn.execute(count_sql, params).fetchone()["cnt"]

        # Fetch page
        offset = (page - 1) * per_page
        query_sql = f"""
            SELECT vs.id as session_id, vs.application_id, a.brand_name,
                   vs.beverage_type, vs.status, vs.overall_confidence,
                   vs.agent_decision, vs.created_at,
                   vs.processing_time_ms, vs.total_input_tokens,
                   vs.total_output_tokens, vs.estimated_cost_usd
            FROM verification_sessions vs
            LEFT JOIN applications a ON a.session_id = vs.id
            {where_sql}
            ORDER BY vs.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query_sql, params + [per_page, offset]).fetchall()

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

        return {
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page,
            }
        }
    finally:
        conn.close()
