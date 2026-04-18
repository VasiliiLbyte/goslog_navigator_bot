"""Конфигурация приложения — все параметры берутся из .env через Pydantic Settings."""

from typing import Literal

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
    telegram_proxy_url: str | None = None  # например http://127.0.0.1:10809

    # Ofdata / FNS (ИНН -> автозаполнение ЕГРИП/ЕГРЮЛ)
    # Важно: ключ может быть не задан для локального тестирования — тогда wizard уйдёт в fallback.
    fns_api_base_url: str = "https://api.ofdata.ru/v2"
    fns_api_key: SecretStr | None = None
    fns_http_timeout_sec: float = 15.0

    # Публичная проверка реестра ГосЛог (HTML/JSON — зависит от фактического API сайта)
    goslog_public_check_url: str = "https://goslog.ru/check"
    goslog_http_timeout_sec: float = 12.0

    # Ежедневные алерты (AsyncIOScheduler, часовой пояс IANA)
    daily_alerts_enabled: bool = True
    daily_alerts_hour: int = 9
    daily_alerts_minute: int = 0
    daily_alerts_timezone: str = "Europe/Moscow"

    # YooKassa
    yookassa_shop_id: str | None = None
    yookassa_secret_key: SecretStr | None = None
    yookassa_return_url: str = "https://t.me"

    # PostgreSQL
    db_url: str  # asyncpg DSN: postgresql+asyncpg://user:pass@host:5432/db
    db_create_all_fallback: bool = False

    # Redis (для FSM storage)
    redis_url: str = "redis://localhost:6379/0"

    # PDF (временные файлы)
    pdf_temp_dir: str = "goslog_navigator_bot/bot/temp_pdfs"
    pdf_delete_after_send: bool = False

    # Приложение
    bot_mode: Literal["webhook", "polling"] = "webhook"
    debug: bool = False
    log_level: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
