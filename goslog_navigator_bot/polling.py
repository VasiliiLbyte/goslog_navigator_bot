"""Точка входа для запуска Telegram-бота в polling-режиме."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger
from redis.asyncio import Redis

from goslog_navigator_bot.bot.handlers.check import check_router
from goslog_navigator_bot.bot.handlers.start import router as start_router
from goslog_navigator_bot.bot.handlers.wizard import wizard_router
from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.core.logger import setup_logger
from goslog_navigator_bot.database.session import engine
from goslog_navigator_bot.scheduler.daily_alerts import build_scheduler


async def run_polling() -> None:
    """Запуск бота через long polling без webhook."""
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
    dp.include_router(check_router)

    sched = build_scheduler(bot)

    try:
        if sched is not None:
            sched.start()
            logger.info("APScheduler: ежедневные алерты запущены (polling)")
        logger.info("🚀 Запуск бота в polling-режиме...")

        await redis.ping()
        logger.info("Redis подключён: {url}", url=settings.redis_url)

        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
        logger.info("PostgreSQL подключён: OK")

        # В polling-режиме удаляем webhook, чтобы Telegram отдавал апдейты через getUpdates.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook отключён, начинаем polling.")

        await dp.start_polling(bot)
    finally:
        if sched is not None:
            sched.shutdown(wait=False)
            logger.info("APScheduler остановлен (polling)")
        logger.info("⏹ Остановка polling-бота...")
        await bot.session.close()
        await redis.aclose()
        await engine.dispose()
        logger.info("Все подключения закрыты.")


if __name__ == "__main__":
    asyncio.run(run_polling())
