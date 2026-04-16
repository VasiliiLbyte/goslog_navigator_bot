from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from goslog_navigator_bot.database.models import Base


# Alembic Config object, provides access to values within the .ini file.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    # В проекте может не быть полноценной logging-конфигурации в alembic.ini.
    # Alembic не должен падать из-за отсутствия форматтеров.
    try:
        fileConfig(config.config_file_name)
    except (KeyError, ValueError):
        pass

# Target metadata for 'autogenerate' support.
target_metadata = Base.metadata


def _db_url() -> str:
    """
    Возвращает DB URL для миграций.

    Важно: используем окружение (DB_URL из .env), чтобы миграции работали без
    необходимости подставлять секреты в alembic.ini.
    """

    env_url = os.getenv("DB_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Запуск миграций в режиме offline (без фактического подключения)."""

    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Конфигурация контекста миграций для режима online."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Запуск миграций в режиме online (через подключение)."""

    connectable = async_engine_from_config(
        {"sqlalchemy.url": _db_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

