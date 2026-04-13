"""Настройка логирования через loguru — красивый вывод + ротация файлов."""

import sys

from loguru import logger

from goslog_navigator_bot.core.config import settings


def setup_logger() -> None:
    """Инициализация loguru: убираем дефолтный handler, ставим свои."""
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )

    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="DEBUG",
        rotation="00:00",
        retention="14 days",
        compression="gz",
        encoding="utf-8",
    )
