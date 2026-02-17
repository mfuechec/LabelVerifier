from fastapi import Request

from app.db.setup import get_db


def get_db_path(request: Request | None = None) -> str:
    """Get DB path from app state or default."""
    if request and hasattr(request.app.state, "db_path"):
        return request.app.state.db_path
    return "data/labelverify.db"


__all__ = ["get_db", "get_db_path"]
