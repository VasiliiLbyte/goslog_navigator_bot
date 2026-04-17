from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура внизу экрана для удобной навигации."""
    # Быстрые действия для основных сценариев модуля.
    keyboard = [
        [
            KeyboardButton(text="🔍 Проверить контрагента"),
            KeyboardButton(text="📋 Мои контрагенты"),
        ],
        [
            KeyboardButton(text="🛎 Алерты вкл"),
            KeyboardButton(text="🛎 Алерты выкл"),
        ],
        [
            KeyboardButton(text="🏠 Вернуться в начало"),
            KeyboardButton(text="❓ FAQ"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,      # клавиатура всегда видна
        input_field_placeholder="Выберите действие..."
    )
