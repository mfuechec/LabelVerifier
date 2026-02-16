from fastapi import Request

from app.db.setup import get_db
from app.services.orchestrator import VerificationOrchestrator


def get_db_path(request: Request | None = None) -> str:
    """Get DB path from app state or default."""
    if request and hasattr(request.app.state, "db_path"):
        return request.app.state.db_path
    return "data/labelverify.db"


def get_orchestrator(request: Request | None = None) -> VerificationOrchestrator:
    """Create a VerificationOrchestrator with the correct DB path."""
    db_path = get_db_path(request)
    return VerificationOrchestrator(db_path=db_path)


__all__ = ["get_db", "get_db_path", "get_orchestrator"]
