"""Хэндлеры /start и онбординг-флоу."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from goslog_navigator_bot.bot.keyboards.inline import (
    business_type_keyboard,
    okved_keyboard,
)
from goslog_navigator_bot.bot.states.user import OnboardingState

router = Router(name="start")


# ── /start ──────────────────────────────────────────────────────────


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Приветствие и переход к выбору формы бизнеса."""
    logger.info(
        "Пользователь {uid} ({name}) вызвал /start",
        uid=message.from_user.id,  # type: ignore[union-attr]
        name=message.from_user.full_name,  # type: ignore[union-attr]
    )

    await state.set_state(OnboardingState.choosing_business_type)

    await message.answer(
        "👋 <b>Добро пожаловать в ГосЛог Навигатор!</b>\n\n"
        "Я помогу разобраться с требованиями системы ГосЛог "
        "и подготовить ваш бизнес к подключению.\n\n"
        "Для начала — какая у вас форма бизнеса?",
        reply_markup=business_type_keyboard(),
    )


# ── Выбор ИП / ООО ─────────────────────────────────────────────────


@router.callback_query(
    OnboardingState.choosing_business_type,
    F.data.startswith("biz:"),
)
async def on_business_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Сохраняем тип бизнеса и спрашиваем про ОКВЭД."""
    biz_type = callback.data.split(":")[1]  # type: ignore[union-attr]
    label = "ИП" if biz_type == "ip" else "ООО"

    await state.update_data(business_type=biz_type)
    await state.set_state(OnboardingState.checking_okved)

    logger.info("Пользователь {uid} выбрал {biz}", uid=callback.from_user.id, biz=label)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Отлично, вы — <b>{label}</b>.\n\n"
        "Теперь важный вопрос: есть ли у вас ОКВЭД <b>52.29</b> "
        "(«Деятельность вспомогательная прочая, связанная с перевозками»)?",
        reply_markup=okved_keyboard(),
    )

    await callback.answer()


# ── Ответ про ОКВЭД ────────────────────────────────────────────────


@router.callback_query(
    OnboardingState.checking_okved,
    F.data.startswith("okved:"),
)
async def on_okved_answer(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка ответа по ОКВЭД 52.29."""
    answer = callback.data.split(":")[1]  # type: ignore[union-attr]

    logger.info(
        "Пользователь {uid} ответил по ОКВЭД: {ans}",
        uid=callback.from_user.id,
        ans=answer,
    )

    if answer == "yes":
        await state.update_data(has_okved_5229=True)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "✅ ОКВЭД 52.29 есть — значит, подключение к ГосЛог для вас <b>обязательно</b>.\n\n"
            "Скоро я покажу пошаговый план. Следите за обновлениями!",
        )
        await state.clear()

    elif answer == "no":
        await state.update_data(has_okved_5229=False)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "ℹ️ Без ОКВЭД 52.29 подключение к ГосЛог пока <b>не требуется</b>.\n\n"
            "Но если планируете добавить этот вид деятельности — "
            "возвращайтесь, я помогу!",
        )
        await state.clear()

    elif answer == "check_inn":
        await state.set_state(OnboardingState.waiting_inn)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "🔍 <b>Автоматическая проверка по ИНН</b>\n\n"
            "🚧 Эта функция в разработке — скоро будет автозаполнение.\n"
            "Пока вы можете проверить ОКВЭД вручную на сайте ФНС:\n"
            "https://egrul.nalog.ru/\n\n"
            "Введите /start, чтобы начать заново.",
        )

    await callback.answer()
