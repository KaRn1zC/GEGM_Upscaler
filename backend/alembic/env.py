"""Configuration Alembic pour migrations async avec SQLAlchemy.

Charge la configuration depuis l'application (pydantic-settings) et
utilise ``run_sync`` pour exécuter les migrations via le moteur async asyncpg.
"""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Enregistrement de tous les modèles pour que Base.metadata
# contienne la définition complète du schéma.
from app.core.audit import AuditLog  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.jobs.models import Job  # noqa: F401
from app.users.models import User  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Génère le SQL de migration sans connexion à la base.

    Utile pour inspecter le SQL avant de l'appliquer manuellement.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: object) -> None:
    """Exécute les migrations dans le contexte d'une connexion synchrone."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crée un moteur async, ouvre une connexion et lance les migrations."""
    connectable = create_async_engine(settings.DATABASE_URL)

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Exécute les migrations en mode online (connexion active à la DB)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
