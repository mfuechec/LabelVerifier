from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
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


settings = Settings()
