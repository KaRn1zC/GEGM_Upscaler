"""Tests du module users.

Couvre :
- ``get_or_create_by_email`` (service) : création et retour d'un user existant.
- ``GET /api/users/me`` : endpoint d'identité, déclenche l'auto-provisioning
  à la première connexion puis retourne l'utilisateur existant aux suivantes.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.users.service import get_or_create_by_email
from tests.conftest import AUTH_HEADERS


async def test_should_create_new_user_when_absent(db: AsyncSession) -> None:
    """``get_or_create_by_email`` crée un nouvel utilisateur s'il n'existe pas."""
    user = await get_or_create_by_email(db, email="nouveau@gegm.local", name="Nouveau")

    assert user.id is not None
    assert user.email == "nouveau@gegm.local"
    assert user.name == "Nouveau"

    # Vérification DB : le user est bien persisté.
    result = await db.execute(select(User).where(User.email == "nouveau@gegm.local"))
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.id == user.id


async def test_should_return_existing_user_when_present(db: AsyncSession) -> None:
    """``get_or_create_by_email`` retourne l'utilisateur existant sans le dupliquer."""
    existing = User(email="deja-la@gegm.local", name="Existant")
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    retrieved = await get_or_create_by_email(db, email="deja-la@gegm.local", name="Ignoré")

    assert retrieved.id == existing.id
    # Le nom passé en argument est ignoré : on n'écrase pas la valeur existante.
    assert retrieved.name == "Existant"


async def test_should_not_update_name_on_existing_user(db: AsyncSession) -> None:
    """Le nom en argument est ignoré pour ne pas écraser un nom custom en DB."""
    user = User(email="custom-name@gegm.local", name="Nom Custom")
    db.add(user)
    await db.commit()

    await get_or_create_by_email(db, email="custom-name@gegm.local", name="Nom Différent")
    await db.refresh(user)

    assert user.name == "Nom Custom"


async def test_should_handle_none_name(db: AsyncSession) -> None:
    """Accepte un ``name=None`` (cas du token statique sans claims détaillés)."""
    user = await get_or_create_by_email(db, email="sansnom@gegm.local", name=None)

    assert user.email == "sansnom@gegm.local"
    assert user.name is None


async def test_get_me_creates_user_on_first_call(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """``GET /api/users/me`` auto-provisionne l'utilisateur à la 1re connexion.

    Le token statique de test (``test-token``) retourne un ``AuthenticatedUser``
    fixe avec ``email=pytest@test.local``. Premier appel → user créé.
    """
    response = await client.get("/api/users/me", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "pytest@test.local"
    assert body["name"] == "Pytest User"
    assert "id" in body
    assert "created_at" in body

    # Le user doit exister en DB maintenant.
    result = await db.execute(select(User).where(User.email == "pytest@test.local"))
    found = result.scalar_one_or_none()
    assert found is not None


async def test_get_me_returns_existing_user_on_subsequent_calls(
    client: AsyncClient,
) -> None:
    """Deux appels successifs retournent le même utilisateur (pas de duplication)."""
    first = await client.get("/api/users/me", headers=AUTH_HEADERS)
    second = await client.get("/api/users/me", headers=AUTH_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_get_me_requires_authentication(client: AsyncClient) -> None:
    """``GET /api/users/me`` sans token → 401."""
    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_get_me_rejects_invalid_token(client: AsyncClient) -> None:
    """``GET /api/users/me`` avec mauvais token → 401."""
    response = await client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer mauvais-token"},
    )
    assert response.status_code == 401


async def test_get_me_accepts_token_via_query_param(client: AsyncClient) -> None:
    """Fallback auth : token en query param accepté (pour les balises HTML natives)."""
    response = await client.get("/api/users/me?token=test-token")
    assert response.status_code == 200
    assert response.json()["email"] == "pytest@test.local"
