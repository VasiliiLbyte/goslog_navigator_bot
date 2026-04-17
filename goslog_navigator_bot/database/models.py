"""SQLAlchemy 2.x модели — декларативный стиль с mapped_column."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    business_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "ip" | "ooo"
    has_okved_5229: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Модуль 3: ежедневные алерты в Telegram
    daily_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # ИНН «себя» для проверки включения в реестр ГосЛог в рамках утреннего отчёта
    own_inn_for_alerts: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # Модуль 4: единичная активная подписка пользователя (freemium/billing).
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription",
        uselist=False,
        back_populates="user",
    )


class WizardSession(Base):
    """Сессия мастера онбординга — для будущего расширения."""

    __tablename__ = "wizard_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # Строка названия шага FSM. Например: waiting_for_inn / generating_pdf / finished.
    step: Mapped[str] = mapped_column(String(50), default="waiting_for_inn")
    # JSONB-хранилище всего прогресса wizard. По требованиям модуля 2 — типизация dict.
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Counterparty(Base):
    """
    Контрагент, проверенный пользователем по ИНН (модуль 3).

    Храним снимок последней проверки + флаг по публичному реестру ГосЛог.
    """

    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("user_id", "inn", name="uq_counterparties_user_inn"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    inn: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    okved_main: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okved_extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reg_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # True — в реестре, False — не найден, None — не удалось определить
    in_goslog_registry: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    goslog_check_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    needs_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw_ofdata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Subscription(Base):
    """Подписка пользователя (freemium + платные тарифы)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="subscription")


async def create_all_tables() -> None:
    """
    Временный фикс: создать все таблицы по метаданным ORM (в т.ч. counterparties).

    Предпочтительно использовать Alembic; эта функция страхует отсутствие миграций.
    """
    from goslog_navigator_bot.database.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
