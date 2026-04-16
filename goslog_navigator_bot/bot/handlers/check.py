"""
Модуль 3: проверка контрагентов по ИНН и управление утренними алертами.

Команды (кириллица): /проверить_инн, /контрагенты, /алерты_вкл, /алерты_выкл, /мой_инн
"""

from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from loguru import logger

from goslog_navigator_bot.bot.handlers.wizard import _normalize_inn
from goslog_navigator_bot.bot.states.user import AlertsOwnInnState, CheckINNState
from goslog_navigator_bot.database.repositories.counterparties import (
    list_counterparties_for_user,
    upsert_counterparty_from_check,
)
from goslog_navigator_bot.database.repositories.user_profiles import (
    ensure_user,
    set_daily_alerts,
    set_own_inn_for_alerts,
)
from goslog_navigator_bot.database.session import async_session
from goslog_navigator_bot.services.counterparty_verify import (
    InnCheckResult,
    format_inn_card,
    format_registry_line,
    run_inn_check,
)

check_router = Router(name="check")

DISCLAIMER = "Это помощник, не юридическая консультация."


def _d() -> str:
    """Дисклеймер в конце каждого ответа."""
    return f"\n\n{DISCLAIMER}"


def _postpone() -> str:
    return "Сервисы проверки сейчас недоступны. Проверим позже." + _d()


async def daily_alerts() -> None:
    """Заглушка для APScheduler; позже — реальная перепроверка подписчиков."""
    logger.info("🔔 Ежедневные алерты запущены (пока пустые)")


async def _check_counterparty(inn: str, user_id: int) -> InnCheckResult:
    """Проверка ИНН через внешние API + сохранение снимка в Counterparty."""
    result = await run_inn_check(inn)
    async with async_session() as session:
        await upsert_counterparty_from_check(session, user_id=user_id, result=result)
        await session.commit()
    return result


@check_router.message(Command("проверить_инн"))
async def cmd_check_inn(message: Message, state: FSMContext) -> None:
    """Старт сценария: ждём ИНН от пользователя."""
    uid = message.from_user.id  # type: ignore[union-attr]
    logger.info("Модуль3: пользователь {uid} вызвал /проверить_инн", uid=uid)
    await state.set_state(CheckINNState.waiting_for_inn)
    await message.answer(
        "Введите <b>ИНН</b> контрагента (10 цифр для ООО или 12 для ИП).\n"
        "Я запрошу данные Ofdata и попробую сверить открытый реестр ГосЛог."
        + _d()
    )


@check_router.message(StateFilter(CheckINNState.waiting_for_inn), F.text)
async def on_inn_input(message: Message, state: FSMContext) -> None:
    """Текстовый ввод ИНН после /проверить_инн: проверка, БД, карточка."""
    uid = message.from_user.id  # type: ignore[union-attr]
    inn = _normalize_inn((message.text or "").strip())
    logger.info("Модуль3: пользователь {uid} прислал ИНН для проверки", uid=uid)

    if len(inn) not in (10, 12):
        await message.answer(
            "ИНН должен содержать ровно <b>10</b> или <b>12</b> цифр.\n"
            "Попробуйте ещё раз или /проверить_инн."
            + _d()
        )
        return

    try:
        result = await _check_counterparty(inn, uid)
    except httpx.HTTPError as e:
        logger.warning("Модуль3: httpx при проверке ИНН uid={uid}: {e!s}", uid=uid, e=e)
        await state.clear()
        await message.answer(_postpone())
        return
    except Exception:
        logger.exception("Модуль3: сбой _check_counterparty uid={uid}", uid=uid)
        await state.clear()
        await message.answer(_postpone())
        return

    logger.info("Модуль3: контрагент сохранён uid={uid} inn={inn}", uid=uid, inn=inn)
    await state.clear()
    await message.answer(format_inn_card(result) + _d())


@check_router.message(Command("контрагенты"))
async def cmd_counterparties_list(message: Message) -> None:
    """Список всех проверенных контрагентов пользователя."""
    uid = message.from_user.id  # type: ignore[union-attr]
    logger.info("Модуль3: пользователь {uid} вызвал /контрагенты", uid=uid)
    try:
        async with async_session() as session:
            rows = await list_counterparties_for_user(session, uid)
    except Exception:
        logger.exception("Модуль3: ошибка чтения списка uid={uid}", uid=uid)
        await message.answer(_postpone())
        return

    if not rows:
        await message.answer(
            "У вас пока нет сохранённых проверок. Используйте /проверить_инн." + _d()
        )
        return

    lines: list[str] = ["<b>Ваши контрагенты</b>", ""]
    for c in rows:
        reg = format_registry_line(c.in_goslog_registry)
        mark = "⚠️" if c.needs_attention else ""
        name = c.display_name or "—"
        lines.append(
            f"• <code>{c.inn}</code> {mark}\n"
            f"  {name}\n"
            f"  {reg}\n"
            f"  ОКВЭД: {c.okved_main or '—'}\n"
            f"  Статус: {c.status_text or '—'}"
        )
    text = "\n\n".join(lines) + _d()
    if len(text) > 4000:
        text = text[:3900] + "\n\n… (список обрезан)" + _d()
    await message.answer(text)


@check_router.message(Command("алерты_вкл"))
async def cmd_alerts_on(message: Message) -> None:
    """Включаем «подписку» на ежедневные сообщения (флаг в БД)."""
    uid = message.from_user.id  # type: ignore[union-attr]
    fu = message.from_user  # type: ignore[union-attr]
    logger.info("Модуль3: пользователь {uid} включил алерты", uid=uid)
    try:
        async with async_session() as session:
            await ensure_user(
                session,
                user_id=uid,
                username=fu.username,
                full_name=fu.full_name or "—",
            )
            await set_daily_alerts(session, uid, True)
            await session.commit()
    except Exception:
        logger.exception("Модуль3: ошибка включения алертов uid={uid}", uid=uid)
        await message.answer(_postpone())
        return

    await message.answer(
        "✅ Утренние алерты <b>включены</b> (около 9:00 по Москве).\n"
        "При желании укажите свой ИНН для проверки в реестре: /мой_инн"
        + _d()
    )


@check_router.message(Command("алерты_выкл"))
async def cmd_alerts_off(message: Message) -> None:
    uid = message.from_user.id  # type: ignore[union-attr]
    logger.info("Модуль3: пользователь {uid} выключил алерты", uid=uid)
    try:
        async with async_session() as session:
            await set_daily_alerts(session, uid, False)
            await session.commit()
    except Exception:
        logger.exception("Модуль3: ошибка выключения алертов uid={uid}", uid=uid)
        await message.answer(_postpone())
        return

    await message.answer("Утренние алерты <b>выключены</b>." + _d())


@check_router.message(Command("мой_инн"))
async def cmd_own_inn(message: Message, state: FSMContext) -> None:
    """Сохраняем ИНН «себя» для утренней сверки с ГосЛог."""
    uid = message.from_user.id  # type: ignore[union-attr]
    logger.info("Модуль3: пользователь {uid} начал ввод своего ИНН", uid=uid)
    await state.set_state(AlertsOwnInnState.waiting_own_inn)
    await message.answer(
        "Введите <b>ваш ИНН</b> (10 или 12 цифр) для утреннего отчёта по реестру ГосЛог.\n"
        "Отмена: /алерты_выкл или другой раздел бота после завершения."
        + _d()
    )


@check_router.message(StateFilter(AlertsOwnInnState.waiting_own_inn), F.text)
async def on_own_inn(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id  # type: ignore[union-attr]
    fu = message.from_user  # type: ignore[union-attr]
    inn = _normalize_inn(message.text or "")
    logger.info("Модуль3: пользователь {uid} прислал свой ИНН", uid=uid)
    if len(inn) not in (10, 12):
        await message.answer("Нужен ИНН из 10 или 12 цифр. Попробуйте снова или /мой_инн." + _d())
        return
    try:
        async with async_session() as session:
            await ensure_user(
                session,
                user_id=uid,
                username=fu.username,
                full_name=fu.full_name or "—",
            )
            await set_own_inn_for_alerts(session, uid, inn)
            await session.commit()
    except Exception:
        logger.exception("Модуль3: ошибка сохранения своего ИНН uid={uid}", uid=uid)
        await state.clear()
        await message.answer(_postpone())
        return

    await state.clear()
    await message.answer(f"Сохранён ваш ИНН: <code>{inn}</code>." + _d())
