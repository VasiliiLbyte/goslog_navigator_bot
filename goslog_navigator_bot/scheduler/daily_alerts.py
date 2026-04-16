"""
Ежедневные алерты (APScheduler + AsyncIO): перепроверка контрагентов и «своего» ИНН.

Подписка = флаг users.daily_alerts_enabled (вкл. командой /алерты_вкл).
"""

from __future__ import annotations

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.database.repositories.counterparties import (
    list_counterparties_for_user,
    upsert_counterparty_from_check,
)
from goslog_navigator_bot.database.repositories.user_profiles import list_alert_subscribers
from goslog_navigator_bot.database.session import async_session
from goslog_navigator_bot.services.counterparty_verify import format_registry_line, run_inn_check

DISCLAIMER = "Это помощник, не юридическая консультация."


def _disclaimer_suffix() -> str:
    return f"\n\n{DISCLAIMER}"


async def run_daily_alerts_job(bot: Bot) -> None:
    """Утренний проход: обновляем данные и шлём краткую сводку подписчикам."""
    if not settings.daily_alerts_enabled:
        logger.info("daily_alerts: отключено в настройках (DAILY_ALERTS_ENABLED=false)")
        return

    logger.info("daily_alerts: старт задачи")
    async with async_session() as session:
        subscribers = await list_alert_subscribers(session)

    for u in subscribers:
        uid = int(u.id)
        try:
            async with async_session() as session:
                rows = await list_counterparties_for_user(session, uid)
                own_inn = (u.own_inn_for_alerts or "").strip() or None

                if not rows and not own_inn:
                    logger.info(
                        "daily_alerts: uid={uid} — нет контрагентов и ИНН, пропуск",
                        uid=uid,
                    )
                    continue

                not_in_reg = 0
                need_att = 0
                own_line: str | None = None

                for c in rows:
                    try:
                        result = await run_inn_check(c.inn)
                        await upsert_counterparty_from_check(session, user_id=uid, result=result)
                        if result.in_goslog_registry is False:
                            not_in_reg += 1
                        if result.needs_attention:
                            need_att += 1
                    except Exception:
                        logger.exception(
                            "daily_alerts: ошибка перепроверки ИНН={inn} uid={uid}",
                            inn=c.inn,
                            uid=uid,
                        )
                        need_att += 1

                if own_inn:
                    try:
                        own_res = await run_inn_check(own_inn)
                        gl = format_registry_line(own_res.in_goslog_registry)
                        own_line = f"Ваш ИНН в ГосЛог: {gl}"
                        if own_res.in_goslog_registry is False:
                            not_in_reg += 1
                        if own_res.needs_attention:
                            need_att += 1
                    except Exception:
                        logger.exception(
                            "daily_alerts: ошибка проверки своего ИНН uid={uid}",
                            uid=uid,
                        )
                        own_line = "Ваш ИНН: проверим позже (сервис недоступен)."
                        need_att += 1

                await session.commit()

            parts = [
                "<b>Алерты на сегодня</b>",
                f"Не в реестре ГосЛог: <b>{not_in_reg}</b> шт.",
                f"Требуют внимания: <b>{need_att}</b> шт.",
            ]
            if own_line:
                parts.append(own_line)
            text = "\n".join(parts) + _disclaimer_suffix()
            await bot.send_message(chat_id=uid, text=text)
            logger.info(
                "daily_alerts: отправлено uid={uid} not_in={n1} need={n2}",
                uid=uid,
                n1=not_in_reg,
                n2=need_att,
            )
        except Exception:
            logger.exception("daily_alerts: сбой для uid={uid}", uid=uid)


def build_scheduler(bot: Bot) -> AsyncIOScheduler | None:
    """Создаёт и настраивает планировщик (вызывающий код должен start/shutdown)."""
    if not settings.daily_alerts_enabled:
        return None

    sched = AsyncIOScheduler(timezone=settings.daily_alerts_timezone)
    sched.add_job(
        run_daily_alerts_job,
        CronTrigger(
            hour=settings.daily_alerts_hour,
            minute=settings.daily_alerts_minute,
            timezone=settings.daily_alerts_timezone,
        ),
        id="goslog_daily_alerts",
        replace_existing=True,
        kwargs={"bot": bot},
    )
    logger.info(
        "Планировщик алертов: {h:02d}:{m:02d} {tz}",
        h=settings.daily_alerts_hour,
        m=settings.daily_alerts_minute,
        tz=settings.daily_alerts_timezone,
    )
    return sched
