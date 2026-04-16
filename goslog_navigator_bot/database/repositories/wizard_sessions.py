from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from goslog_navigator_bot.database.models import WizardSession
from goslog_navigator_bot.database.session import async_session


async def get_or_create_by_user_id(
    user_id: int,
    *,
    initial_step: str = "waiting_for_inn",
    initial_data: Mapping[str, Any] | None = None,
) -> WizardSession:
    """
    Берём активную сессию wizard (если не finished) или создаём новую.

    Почему так:
    - пользователь может перезапускать flow через `/start`
    - при повторном заходе после завершения создаём новую запись, чтобы
      история была стабильной.
    """

    async with async_session() as session:
        stmt = (
            select(WizardSession)
            .where(WizardSession.user_id == user_id)
            .order_by(WizardSession.created_at.desc())
            .limit(1)
        )
        row = await session.scalar(stmt)

        if row is None or row.step == "finished":
            data_dict: dict[str, Any] = dict(initial_data or {})
            row = WizardSession(
                user_id=user_id,
                step=initial_step,
                data=data_dict,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

        return row


async def update_step(user_id: int, step: str) -> None:
    """Обновляем текущий шаг wizard в БД."""

    async with async_session() as session:
        row = await session.scalar(
            select(WizardSession)
            .where(WizardSession.user_id == user_id)
            .order_by(WizardSession.created_at.desc())
            .limit(1)
        )
        if row is None:
            row = WizardSession(user_id=user_id, step=step, data={})
            session.add(row)

        else:
            row.step = step

        await session.commit()


async def merge_data(user_id: int, patch: Mapping[str, Any]) -> None:
    """
    Мягко сливаем patch в JSONB поле `data`.

    Для простоты и надёжности делаем merge на стороне Python (через загрузку row).
    Для текущего MVP этого достаточно.
    """

    async with async_session() as session:
        row = await session.scalar(
            select(WizardSession)
            .where(WizardSession.user_id == user_id)
            .order_by(WizardSession.created_at.desc())
            .limit(1)
        )
        if row is None:
            row = WizardSession(user_id=user_id, step="waiting_for_inn", data=dict(patch))
            session.add(row)
        else:
            # JSONB может быть пустым/None, но по модели default=dict, так что это редкий кейс.
            current = dict(row.data or {})
            current.update(patch)
            row.data = current

        await session.commit()


async def mark_finished(user_id: int, *, status: str = "completed") -> None:
    """Помечаем wizard как завершённый и фиксируем статус в data."""

    await update_step(user_id, "finished")
    await merge_data(user_id, {"status": status})

