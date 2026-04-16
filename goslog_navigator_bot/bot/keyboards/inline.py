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


def wizard_confirm_keyboard() -> InlineKeyboardMarkup:
    """Шаг 2: подтверждение автозаполненных данных."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Всё верно ✅",
                    callback_data="wizard_confirm:ok",
                ),
                InlineKeyboardButton(
                    text="Исправить ✏️",
                    callback_data="wizard_confirm:edit",
                ),
            ]
        ]
    )


def wizard_pdf_keyboard() -> InlineKeyboardMarkup:
    """Шаг 4: генерация PDF или отмена wizard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Генерировать PDF",
                    callback_data="wizard_pdf:generate",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="wizard_pdf:cancel",
                ),
            ]
        ]
    )


def wizard_finish_keyboard() -> InlineKeyboardMarkup:
    """Шаг 5: кнопка завершения после отправки через Госуслуги."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово, отправил", callback_data="wizard_finish:done")]
        ]
    )
