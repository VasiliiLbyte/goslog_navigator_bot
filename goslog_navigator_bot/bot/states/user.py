"""FSM-состояния для онбординга пользователя."""

from aiogram.fsm.state import State, StatesGroup


class OnboardingState(StatesGroup):
    """Мастер первичной настройки после /start."""

    choosing_business_type = State()  # ИП или ООО
    checking_okved = State()          # Есть ли ОКВЭД 52.29
    waiting_inn = State()             # Ввод ИНН (заглушка)
