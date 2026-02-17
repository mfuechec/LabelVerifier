import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import verify, history, feedback, health
from app.db.setup import get_db, create_tables

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings.validate_required()

    app = FastAPI(
        title="LabelVerify AI",
        description="AI-powered alcohol label verification for TTB Compliance",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(verify.router, prefix="/api/v1", tags=["verification"])
    app.include_router(history.router, prefix="/api/v1", tags=["history"])
    app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])

    # Ensure data directories exist
    os.makedirs("data/uploads", exist_ok=True)
    os.makedirs("data/annotated", exist_ok=True)

    # Create database tables on startup
    conn = get_db()
    create_tables(conn)
    conn.close()

    # Log config (redacting secrets) for deploy diagnostics
    redacted_key = (
        settings.groq_api_key[:4] + "***" if settings.groq_api_key else "<not set>"
    )
    logger.info(
        "LabelVerify starting: origins=%s, db=%s, groq_key=%s",
        settings.allowed_origins,
        settings.database_url,
        redacted_key,
    )

    return app


app = create_app()
