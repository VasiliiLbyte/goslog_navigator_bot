"""Async-подключение к PostgreSQL через SQLAlchemy 2.x + asyncpg."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from goslog_navigator_bot.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Фабрика сессий для dependency injection."""
    async with async_session() as session:
        return session
