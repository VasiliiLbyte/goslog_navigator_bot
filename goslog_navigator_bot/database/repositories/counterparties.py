"""Репозиторий контрагентов (модуль 3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from goslog_navigator_bot.database.models import Counterparty
from goslog_navigator_bot.services.counterparty_verify import InnCheckResult


async def upsert_counterparty_from_check(
    session: AsyncSession,
    *,
    user_id: int,
    result: InnCheckResult,
) -> Counterparty:
    """Создаём или обновляем запись по паре (user_id, ИНН)."""
    values = {
        "user_id": user_id,
        "inn": result.inn,
        "display_name": result.display_name,
        "okved_main": result.okved_main,
        "okved_extra": result.okved_extra,
        "status_text": result.status_text,
        "reg_date": result.reg_date,
        "in_goslog_registry": result.in_goslog_registry,
        "goslog_check_note": result.goslog_check_note,
        "needs_attention": result.needs_attention,
        "raw_ofdata": result.raw_ofdata,
    }
    ins = pg_insert(Counterparty).values(**values)
    stmt = ins.on_conflict_do_update(
        index_elements=[Counterparty.user_id, Counterparty.inn],
        set_={
            "display_name": ins.excluded.display_name,
            "okved_main": ins.excluded.okved_main,
            "okved_extra": ins.excluded.okved_extra,
            "status_text": ins.excluded.status_text,
            "reg_date": ins.excluded.reg_date,
            "in_goslog_registry": ins.excluded.in_goslog_registry,
            "goslog_check_note": ins.excluded.goslog_check_note,
            "needs_attention": ins.excluded.needs_attention,
            "raw_ofdata": ins.excluded.raw_ofdata,
        },
    ).returning(Counterparty)
    row = await session.scalar(stmt)
    assert row is not None
    return row


async def list_counterparties_for_user(session: AsyncSession, user_id: int) -> list[Counterparty]:
    res = await session.scalars(
        select(Counterparty)
        .where(Counterparty.user_id == user_id)
        .order_by(Counterparty.last_checked_at.desc())
    )
    return list(res.all())
