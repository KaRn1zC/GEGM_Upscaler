"""Configuration du logging Loguru.

Sortie JSON structurée sur stdout pour ingestion Promtail/Loki en production.
Sortie colorée lisible en développement.
"""

import sys

from loguru import logger

from app.core.config import settings


def setup_logging() -> None:
    """Initialise Loguru avec le format de sortie adapté à l'environnement.

    Production : JSON sérialisé sur stdout (consommé par Promtail -> Loki).
    Développement : format coloré lisible avec diagnostics complets.
    """
    logger.remove()

    if settings.is_development:
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stdout,
            format="{message}",
            serialize=True,
            level="INFO",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
