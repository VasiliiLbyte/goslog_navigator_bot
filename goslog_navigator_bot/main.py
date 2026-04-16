"""Точка входа — FastAPI + aiogram webhook + lifespan для Redis/DB."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from redis.asyncio import Redis

from goslog_navigator_bot.bot.handlers.start import router as start_router
from goslog_navigator_bot.bot.handlers.wizard import wizard_router
from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.core.logger import setup_logger
from goslog_navigator_bot.database.session import engine

# ── Инициализация ───────────────────────────────────────────────────

setup_logger()

redis = Redis.from_url(settings.redis_url, decode_responses=True)
storage = RedisStorage(redis=redis)

bot_session = (
    AiohttpSession(proxy=settings.telegram_proxy_url)
    if settings.telegram_proxy_url
    else AiohttpSession()
)

bot = Bot(
    token=settings.bot_token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=bot_session,
)

dp = Dispatcher(storage=storage)
dp.include_router(start_router)
dp.include_router(wizard_router)


# ── Lifespan: startup / shutdown ────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """При старте — webhook + проверка коннектов; при остановке — cleanup."""
    logger.info("🚀 Запуск ГосЛог Навигатор бота...")

    # Устанавливаем webhook только в webhook-режиме.
    if settings.bot_mode == "webhook":
        webhook_url = f"{settings.webhook_url}/webhook"
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        logger.info("Webhook установлен: {url}", url=webhook_url)
    else:
        logger.warning(
            "BOT_MODE={mode}: webhook не устанавливается, используйте polling entrypoint.",
            mode=settings.bot_mode,
        )

    # Проверяем Redis
    await redis.ping()
    logger.info("Redis подключён: {url}", url=settings.redis_url)

    # Проверяем PostgreSQL
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    logger.info("PostgreSQL подключён: OK")

    yield

    # Shutdown
    logger.info("⏹ Остановка бота...")
    if settings.bot_mode == "webhook":
        await bot.delete_webhook()
    await bot.session.close()
    await redis.aclose()
    await engine.dispose()
    logger.info("Все подключения закрыты.")


# ── FastAPI ─────────────────────────────────────────────────────────

app = FastAPI(
    title="ГосЛог Навигатор",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    """Принимаем update от Telegram и передаём в Dispatcher."""
    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return JSONResponse(content={"ok": True})


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck для мониторинга / Docker."""
    return {"status": "ok"}
