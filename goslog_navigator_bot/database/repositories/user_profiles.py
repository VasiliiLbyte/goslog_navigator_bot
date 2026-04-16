"""Профиль пользователя в БД (модуль 3: алерты)."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from goslog_navigator_bot.database.models import User


async def ensure_user(
    session: AsyncSession,
    *,
    user_id: int,
    username: str | None,
    full_name: str,
) -> User:
    """Создаём строку users при первом обращении к функциям, требующим БД."""
    existing = await session.scalar(select(User).where(User.id == user_id))
    if existing:
        return existing
    row = User(
        id=user_id,
        username=username,
        full_name=full_name or "—",
    )
    session.add(row)
    await session.flush()
    return row


async def set_daily_alerts(session: AsyncSession, user_id: int, enabled: bool) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(daily_alerts_enabled=enabled)
    )


async def set_own_inn_for_alerts(session: AsyncSession, user_id: int, inn: str | None) -> None:
    await session.execute(update(User).where(User.id == user_id).values(own_inn_for_alerts=inn))


async def list_alert_subscribers(session: AsyncSession) -> list[User]:
    res = await session.scalars(select(User).where(User.daily_alerts_enabled.is_(True)))
    return list(res.all())
