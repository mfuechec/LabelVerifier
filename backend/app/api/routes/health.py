import os

from fastapi import APIRouter

from app.config import settings
from app.db.setup import get_db

router = APIRouter()

BUILD_SHA = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "local")


@router.get("/health")
async def health_check():
    checks = {"api_key_configured": bool(settings.anthropic_api_key)}
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())
    return {
        "data": {
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
            "version": BUILD_SHA,
        }
    }
