"""FSM-состояния для онбординга пользователя."""

from aiogram.fsm.state import State, StatesGroup


class OnboardingState(StatesGroup):
    """Мастер первичной настройки после /start."""

    choosing_business_type = State()  # ИП или ООО
    checking_okved = State()          # Есть ли ОКВЭД 52.29
    waiting_inn = State()             # Ввод ИНН (заглушка)


class GoslogWizardState(StatesGroup):
    """5-шаговый wizard регистрации/подготовки к подаче в ГосЛог."""

    waiting_for_inn = State()  # Шаг 1: ввод ИНН
    waiting_for_confirmation = State()  # Шаг 2: подтверждение автоданных
    waiting_for_phone_email = State()  # Шаг 3: телефон/email/адрес
    generating_pdf = State()  # Шаг 4: генерация PDF
    finished = State()  # Шаг 5: инструкция + завершение


class CounterpartyCheckState(StatesGroup):
    """Модуль 3: ввод ИНН для проверки контрагента."""

    waiting_inn = State()


class AlertsOwnInnState(StatesGroup):
    """Модуль 3: ввод собственного ИНН для утренней проверки реестра ГосЛог."""

    waiting_own_inn = State()
