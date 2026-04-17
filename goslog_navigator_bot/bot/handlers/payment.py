"""Модуль 4: тарифы и оплата через ЮKassa."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger
from sqlalchemy import select
from yookassa import Configuration, Payment

from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.database.models import Subscription
from goslog_navigator_bot.database.repositories.user_profiles import ensure_user
from goslog_navigator_bot.database.session import async_session

payment_router = Router(name="payment")

DISCLAIMER = "Это помощник, не юридическая консультация."

PLAN_AMOUNT = {
    "start": Decimal("490.00"),
    "business": Decimal("990.00"),
}


def _d() -> str:
    return f"\n\n{DISCLAIMER}"


def _payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Купить Start 490 ₽",
                    callback_data="pay:buy:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Купить Business 990 ₽",
                    callback_data="pay:buy:business",
                )
            ],
        ]
    )


def _configure_yookassa() -> None:
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise RuntimeError("YooKassa credentials are not configured")
    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret_key.get_secret_value()


def _coerce_tier(value: str | None) -> str:
    if value in {"start", "business"}:
        return value
    return "free"


async def _get_subscription_for_user(user_id: int) -> Subscription | None:
    async with async_session() as session:
        return await session.scalar(select(Subscription).where(Subscription.user_id == user_id))


def _format_subscription_line(sub: Subscription | None) -> str:
    now = datetime.now(UTC)
    if not sub or sub.expires_at <= now:
        return "Текущий тариф: <b>free</b>\nЛимит: 3 проверки контрагентов в месяц."
    return (
        f"Текущий тариф: <b>{sub.tier}</b>\n"
        f"Действует до: <code>{sub.expires_at.astimezone().strftime('%Y-%m-%d %H:%M')}</code>\n"
        "Лимит проверок: <b>без ограничений</b>."
    )


def _payment_payload(*, user_id: int, tier: str, amount: Decimal) -> dict:
    return {
        "amount": {"value": str(amount), "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url,
        },
        "description": f"GosLog Navigator подписка: {tier}",
        "metadata": {
            "user_id": str(user_id),
            "tier": tier,
        },
    }


def _extract_confirmation_url(payment_obj: object) -> str | None:
    confirmation = getattr(payment_obj, "confirmation", None)
    if confirmation is None:
        return None
    return getattr(confirmation, "confirmation_url", None)


async def _create_payment(*, user_id: int, tier: str) -> tuple[str, str | None]:
    _configure_yookassa()
    amount = PLAN_AMOUNT[tier]
    payload = _payment_payload(user_id=user_id, tier=tier, amount=amount)
    payment_obj = await asyncio.to_thread(Payment.create, payload, str(uuid4()))
    payment_id = str(payment_obj.id)
    return payment_id, _extract_confirmation_url(payment_obj)


async def _upsert_subscription(
    *,
    user_id: int,
    tier: str,
    payment_id: str | None,
) -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=30)
    async with async_session() as session:
        await ensure_user(
            session,
            user_id=user_id,
            username=None,
            full_name="Пользователь",
        )
        sub = await session.scalar(select(Subscription).where(Subscription.user_id == user_id))
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                tier=tier,
                starts_at=now,
                expires_at=expires_at,
                payment_id=payment_id,
            )
            session.add(sub)
        else:
            sub.tier = tier
            sub.starts_at = now
            sub.expires_at = expires_at
            sub.payment_id = payment_id
        await session.commit()


@payment_router.message(Command("тариф"))
@payment_router.message(F.text == "💰 Тариф")
async def cmd_tariff(message: Message) -> None:
    """Показывает текущий тариф и варианты оплаты."""
    uid = message.from_user.id  # type: ignore[union-attr]
    sub = await _get_subscription_for_user(uid)
    await message.answer(
        "<b>Тарифы GosLog Navigator</b>\n\n"
        f"{_format_subscription_line(sub)}\n\n"
        "Start — 490 ₽/мес\n"
        "Business — 990 ₽/мес",
        reply_markup=_payment_keyboard(),
    )
    await message.answer("Для оплаты используйте кнопки ниже." + _d())


@payment_router.callback_query(F.data.startswith("pay:buy:"))
async def on_buy_plan(callback: CallbackQuery) -> None:
    """Создаёт платёж в ЮKassa и отдаёт ссылку на оплату."""
    uid = callback.from_user.id
    tier = _coerce_tier(callback.data.split(":")[-1] if callback.data else None)
    if tier == "free":
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    try:
        async with async_session() as session:
            await ensure_user(
                session,
                user_id=uid,
                username=callback.from_user.username,
                full_name=callback.from_user.full_name or "—",
            )
            await session.commit()
        payment_id, confirmation_url = await _create_payment(user_id=uid, tier=tier)
        await _upsert_subscription(user_id=uid, tier="free", payment_id=payment_id)
    except Exception:
        logger.exception("payment create failed uid={uid} tier={tier}", uid=uid, tier=tier)
        await callback.message.answer(
            "Сервис оплаты временно недоступен. Попробуйте позже." + _d()
        )
        await callback.answer()
        return

    amount = PLAN_AMOUNT[tier]
    if confirmation_url:
        text = (
            f"Счёт на тариф <b>{tier}</b> ({amount} ₽) создан.\n"
            f"Откройте ссылку для оплаты:\n{confirmation_url}"
        )
    else:
        text = (
            f"Счёт на тариф <b>{tier}</b> ({amount} ₽) создан.\n"
            f"ID платежа: <code>{payment_id}</code>"
        )
    await callback.message.answer(text + _d())
    await callback.answer("Ссылка на оплату отправлена")


async def process_yookassa_webhook(payload: dict) -> dict[str, object]:
    """
    Обработка webhook ЮKassa.

    Обновляет подписку пользователя на 30 дней после успешной оплаты.
    """
    event = str(payload.get("event") or "")
    obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
    payment_id = str(obj.get("id") or "")
    status = str(obj.get("status") or "")
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    user_id_raw = metadata.get("user_id")
    tier = _coerce_tier(str(metadata.get("tier") or "free"))

    if event != "payment.succeeded" or status != "succeeded":
        return {"ok": True, "processed": False, "reason": "event_not_supported"}
    if not payment_id or user_id_raw is None:
        return {"ok": False, "processed": False, "reason": "missing_payment_data"}

    try:
        user_id = int(str(user_id_raw))
    except ValueError:
        return {"ok": False, "processed": False, "reason": "invalid_user_id"}

    await _upsert_subscription(user_id=user_id, tier=tier, payment_id=payment_id)
    logger.info(
        "yookassa webhook processed uid={uid} tier={tier} payment_id={pid}",
        uid=user_id,
        tier=tier,
        pid=payment_id,
    )
    return {"ok": True, "processed": True}
