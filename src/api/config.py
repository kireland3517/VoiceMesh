"""Configuration management for VoiceMesh API."""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8080

    # Database
    DATABASE_URL: str = ""

    # Redis
    REDIS_URL: Optional[str] = None

    # Voice Services
    DEEPGRAM_API_KEY: str = ""
    CARTESIA_API_KEY: str = ""
    DAILY_API_KEY: str = ""  # For Daily.co SIP bridge

    # LLM
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: Optional[str] = None

    # Telephony
    SIGNALWIRE_PROJECT_ID: str = ""
    SIGNALWIRE_TOKEN: str = ""
    SIGNALWIRE_SPACE: str = ""

    # Object Storage (Tigris)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_ENDPOINT_URL_S3: str = "https://fly.storage.tigris.dev"
    BUCKET_NAME: str = ""

    # Security
    JWT_SECRET_KEY: str = ""
    API_KEY_SALT: str = ""

    # Optional: Monitoring
    SENTRY_DSN: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENV == "development"


settings = Settings()
