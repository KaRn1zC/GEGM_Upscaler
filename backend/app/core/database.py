"""Session async SQLAlchemy et moteur de connexion PostgreSQL.

Configure le moteur asynchrone (asyncpg), la session factory et expose
la classe ``Base`` déclarative partagée par tous les modèles ORM du projet.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Classe de base déclarative pour tous les modèles SQLAlchemy du projet."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Fournit une session DB pour l'injection via ``Depends(get_db)``.

    La session est fermée automatiquement à la sortie du contexte.
    Le commit et le rollback restent à la charge de la couche service.

    Yields:
        Session asynchrone SQLAlchemy connectée à PostgreSQL.
    """
    async with async_session_factory() as session:
        yield session
