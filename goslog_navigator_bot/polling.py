"""Точка входа для запуска Telegram-бота в polling-режиме."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from redis.asyncio import Redis

from goslog_navigator_bot.bot.handlers.check import check_router, daily_alerts
from goslog_navigator_bot.bot.handlers.start import router as start_router
from goslog_navigator_bot.bot.handlers.wizard import wizard_router
from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.core.logger import setup_logger
from goslog_navigator_bot.database.models import create_all_tables
from goslog_navigator_bot.database.session import engine


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

    sched: AsyncIOScheduler | None = None
    if settings.daily_alerts_enabled:
        sched = AsyncIOScheduler(timezone=settings.daily_alerts_timezone)
        sched.add_job(
            daily_alerts,
            trigger=CronTrigger(
                hour=settings.daily_alerts_hour,
                minute=settings.daily_alerts_minute,
                timezone=settings.daily_alerts_timezone,
            ),
            id="daily_alerts",
            replace_existing=True,
        )

    try:
        logger.info("🚀 Запуск бота в polling-режиме...")

        await redis.ping()
        logger.info("Redis подключён: {url}", url=settings.redis_url)

        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
        logger.info("PostgreSQL подключён: OK")

        await create_all_tables()
        logger.info("✅ Все таблицы созданы")

        if sched is not None:
            sched.start()
            logger.info("✅ Ежедневные алерты запланированы на 9:00")

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
