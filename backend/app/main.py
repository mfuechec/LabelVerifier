from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import settings
from app.api.routes import verify, history, feedback, health
from app.db.setup import get_db, create_tables


def create_app() -> FastAPI:
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

    return app


app = create_app()
