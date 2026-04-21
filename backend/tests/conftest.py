"""Fixtures partagées pour les tests du backend GEGM Upscaler.

Fournit une session DB transactionnelle (rollback automatique après chaque
test), un backend de stockage temporaire et un client HTTP de test avec
toutes les dépendances injectées.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.pool import NullPool

from app.core.auth.interface import AuthBackend, AuthenticatedUser
from app.core.config import settings
from app.core.dependencies import get_auth, get_db, get_storage
from app.core.storage.local import LocalStorageBackend
from app.main import app

AUTH_HEADERS: dict[str, str] = {"Authorization": "Bearer test-token"}


class _TestAuth(AuthBackend):
    """Backend d'auth des tests — retourne un user isolé de celui du dev local.

    Utilise un email dédié ``pytest@test.local`` (distinct du ``dev@gegm.local``
    du ``StaticTokenAuth`` prod) pour éviter que les tests DB voient les jobs
    créés en dev local réel — l'isolation SAVEPOINT ne couvre pas les writes
    faits hors de la session pytest.
    """

    _TOKEN = "test-token"  # noqa: S105 — fixture de test, pas un vrai secret
    _EMAIL = "pytest@test.local"
    _NAME = "Pytest User"

    async def get_current_user(self, credentials: str) -> AuthenticatedUser:
        if credentials != self._TOKEN:
            raise ValueError("Token invalide")
        return AuthenticatedUser(id="pytest-user", email=self._EMAIL, name=self._NAME)


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Session DB avec isolation transactionnelle via SAVEPOINT.

    Crée un engine dédié avec ``NullPool`` pour éviter les conflits
    d'event loop entre tests. Les ``session.commit()`` de l'application
    s'appliquent sur des SAVEPOINTs, et le rollback final annule tout.
    """
    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)

    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    # Ouvre un premier SAVEPOINT.
    await connection.begin_nested()

    # Après chaque commit (= commit du SAVEPOINT), en rouvrir un.
    @event.listens_for(session.sync_session, "after_transaction_end")
    def _reopen_nested(sync_session: Session, txn: SessionTransaction) -> None:
        if not connection.closed and not connection.in_nested_transaction():
            connection.sync_connection.begin_nested()

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()
    await test_engine.dispose()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    """Backend de stockage local dans un répertoire temporaire jetable."""
    return LocalStorageBackend(base_path=str(tmp_path))


@pytest.fixture
async def client(
    db: AsyncSession,
    storage: LocalStorageBackend,
) -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP de test avec dépendances injectées.

    - DB : session transactionnelle (rollback automatique).
    - Storage : filesystem temporaire.
    - Auth : token statique ``test-token``.
    """

    async def _test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _test_db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_auth] = _TestAuth

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
