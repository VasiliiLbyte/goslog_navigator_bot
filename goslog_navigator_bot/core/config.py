"""Конфигурация приложения — все параметры берутся из .env через Pydantic Settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: SecretStr
    webhook_url: str  # например https://example.com/webhook

    # PostgreSQL
    db_url: str  # asyncpg DSN: postgresql+asyncpg://user:pass@host:5432/db

    # Redis (для FSM storage)
    redis_url: str = "redis://localhost:6379/0"

    # Приложение
    debug: bool = False
    log_level: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
