"""
config.py
=========
Centralised settings via pydantic-settings.
All values are read from environment variables / .env file.

Author : FinMentor Platform
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────
    APP_NAME: str = "FinMentor API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/finmentor"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── JWT ───────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 86_400   # 24 hours

    # ── OpenAI / LLM ─────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_TOKENS: int = 2048

    # ── Rates & defaults ─────────────────────────────────────────────────
    DEFAULT_INFLATION_PCT: float = 6.0
    DEFAULT_PRE_RETIREMENT_RETURN_PCT: float = 12.0
    DEFAULT_POST_RETIREMENT_RETURN_PCT: float = 7.0


settings = Settings()