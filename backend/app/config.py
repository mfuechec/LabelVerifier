import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    reextract_model: str = "claude-haiku-4-5-20251001"
    database_url: str = "sqlite:///./data/labelverify.db"
    allowed_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def validate_required(self):
        """Call on app startup. Raises if critical env vars are missing.

        Skipped when TESTING env var is set (e.g. in pytest).
        """
        if os.environ.get("TESTING"):
            return
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required. "
                "Set it in .env or as an environment variable."
            )


settings = Settings()
