import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    llm_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    database_url: str = "sqlite:///./data/labelverify.db"
    allowed_origins: str = "http://localhost:5173"
    max_image_size: int = 10 * 1024 * 1024  # 10MB
    allowed_mime_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/tiff",
        "application/pdf",
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def validate_required(self):
        """Call on app startup. Raises if critical env vars are missing.

        Skipped when TESTING env var is set (e.g. in pytest).
        """
        if os.environ.get("TESTING"):
            return
        if not self.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is required. Set it in .env or as an environment variable."
            )


settings = Settings()
