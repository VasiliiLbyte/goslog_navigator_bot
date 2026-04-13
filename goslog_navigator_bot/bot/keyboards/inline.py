"""Inline-клавиатуры для онбординга."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def business_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор формы бизнеса: ИП или ООО."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧑‍💼 Я ИП", callback_data="biz:ip"),
                InlineKeyboardButton(text="🏢 Я ООО", callback_data="biz:ooo"),
            ]
        ]
    )


def okved_keyboard() -> InlineKeyboardMarkup:
    """Проверка ОКВЭД 52.29 — три варианта ответа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="okved:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="okved:no"),
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Проверить по ИНН", callback_data="okved:check_inn"
                ),
            ],
        ]
    )
