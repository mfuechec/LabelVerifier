import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_provider: str = "groq"
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "meta-llama/llama-4-maverick-17b-128e-instruct"
    reextract_model: str = "claude-haiku-4-5-20251001"
    database_url: str = "sqlite:///./data/labelverify.db"
    allowed_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def validate_required(self):
        """Call on app startup. Raises if critical env vars are missing.

        Skipped when TESTING env var is set (e.g. in pytest).
        """
        if os.environ.get("TESTING"):
            return
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is required when LLM_PROVIDER is 'groq'. "
                "Set it in .env or as an environment variable."
            )
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER is 'anthropic'. "
                "Set it in .env or as an environment variable."
            )


settings = Settings()
