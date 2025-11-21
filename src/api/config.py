"""Configuration management for VoiceMesh API."""

import os
from typing import Optional


class Settings:
    """Application settings loaded from environment variables."""

    # Application
    ENV: str = os.getenv("ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PORT: int = int(os.getenv("PORT", "8080"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Redis
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    # Voice Services
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    CARTESIA_API_KEY: str = os.getenv("CARTESIA_API_KEY", "")
    DAILY_API_KEY: str = os.getenv("DAILY_API_KEY", "")  # For Daily.co SIP bridge

    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")

    # Telephony
    SIGNALWIRE_PROJECT_ID: str = os.getenv("SIGNALWIRE_PROJECT_ID", "")
    SIGNALWIRE_TOKEN: str = os.getenv("SIGNALWIRE_TOKEN", "")
    SIGNALWIRE_SPACE: str = os.getenv("SIGNALWIRE_SPACE", "")

    # Object Storage (Tigris)
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_ENDPOINT_URL_S3: str = os.getenv("AWS_ENDPOINT_URL_S3", "https://fly.storage.tigris.dev")
    BUCKET_NAME: str = os.getenv("BUCKET_NAME", "")

    # Security
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    API_KEY_SALT: str = os.getenv("API_KEY_SALT", "")

    # Optional: Monitoring
    SENTRY_DSN: Optional[str] = os.getenv("SENTRY_DSN")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENV == "development"


settings = Settings()
