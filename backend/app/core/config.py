from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    Central configuration for the Library Management API.
    All values are read from environment variables (or a .env file).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Project metadata ──────────────────────────────────────────────────────
    PROJECT_NAME: str = "Library Management API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"          # development | staging | production

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./library.db"
    # For PostgreSQL use:
    # DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/library_db"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_EXPIRE_SECONDS: int = 300           # 5 minutes default TTL

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5500", "http://127.0.0.1:5500"]

    # ── Business rules ────────────────────────────────────────────────────────
    MAX_BORROW_LIMIT: int = 5                 # max books a Member can borrow at once

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"


# Single shared instance – import this everywhere
settings = Settings()