"""Tests du flow de suppression RGPD (self-delete + admin-delete).

Couvre :
- ``delete_user_and_data`` : cascade jobs → fichiers → anonymisation → audit.
- ``DELETE /api/users/me`` : enqueue la task Celery + 202 Accepted.
- ``DELETE /api/admin/users/{uuid}`` : guard admin + 404 si absent.
- Auto-provisioning : un user ré-authentifié après purge reçoit un nouvel UUID.
"""

import uuid
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, AuditLog
from app.core.config import settings
from app.core.storage.local import LocalStorageBackend
from app.jobs.models import Job, JobStatus
from app.users.deletion import delete_user_and_data
from app.users.models import User
from app.users.service import get_or_create_by_email
from tests.conftest import AUTH_HEADERS


async def _seed_user_with_jobs(
    db: AsyncSession, storage: LocalStorageBackend, *, email: str = "victim@gegm.local"
) -> tuple[User, list[Job]]:
    """Helper : crée un user + 2 jobs + leurs fichiers sur le storage."""
    user = User(email=email, name="À Purger")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    jobs: list[Job] = []
    for i in range(2):
        input_key = f"uploads/{user.id}/input-{i}.png"
        output_key = f"outputs/{user.id}/output-{i}.png"
        await storage.upload(input_key, b"fake-input-bytes", content_type="image/png")
        await storage.upload(output_key, b"fake-output-bytes", content_type="image/png")

        job = Job(
            user_id=user.id,
            status=JobStatus.COMPLETED.value,
            input_key=input_key,
            output_key=output_key,
            scale_factor=2,
            model_name="drct-l",
            input_width=100,
            input_height=100,
        )
        db.add(job)
        jobs.append(job)
    await db.commit()
    return user, jobs


async def test_delete_user_and_data_removes_jobs_and_files(
    db: AsyncSession, storage: LocalStorageBackend
) -> None:
    """``delete_user_and_data`` supprime jobs + fichiers et anonymise le user."""
    user, jobs = await _seed_user_with_jobs(db, storage)
    input_keys = [j.input_key for j in jobs]
    output_keys = [j.output_key for j in jobs if j.output_key]

    stats = await delete_user_and_data(
        db,
        user.id,
        actor_email=user.email,
        action=AuditAction.USER_SELF_DELETED,
        storage=storage,
    )

    assert stats == {"jobs_deleted": 2, "files_deleted": 4}

    # Jobs supprimés de la DB.
    jobs_remaining = await db.execute(select(Job).where(Job.user_id == user.id))
    assert jobs_remaining.scalar_one_or_none() is None

    # Fichiers supprimés du storage — download() doit lever FileNotFoundError.
    for key in input_keys + output_keys:
        try:
            await storage.download(key)
        except FileNotFoundError:
            continue
        raise AssertionError(f"Fichier {key} devrait être supprimé")

    # User anonymisé (ligne présente, email réécrit, deleted_at posé).
    await db.refresh(user)
    assert user.deleted_at is not None
    assert user.email == f"deleted-{user.id}@deleted.local"
    assert user.name is None


async def test_delete_user_and_data_writes_audit_log(
    db: AsyncSession, storage: LocalStorageBackend
) -> None:
    """Chaque suppression écrit une entrée ``audit_log`` horodatée."""
    user, _ = await _seed_user_with_jobs(db, storage, email="gdpr@gegm.local")

    await delete_user_and_data(
        db,
        user.id,
        actor_email="admin@gegm.local",
        action=AuditAction.USER_ADMIN_DELETED,
        storage=storage,
    )

    result = await db.execute(select(AuditLog).where(AuditLog.target_email == "gdpr@gegm.local"))
    entry = result.scalar_one()
    assert entry.action == AuditAction.USER_ADMIN_DELETED.value
    assert entry.actor_email == "admin@gegm.local"
    assert entry.target_email == "gdpr@gegm.local"
    assert entry.metadata_json is not None
    assert entry.metadata_json["jobs_deleted"] == 2


async def test_delete_user_raises_when_already_deleted(
    db: AsyncSession, storage: LocalStorageBackend
) -> None:
    """Appeler ``delete_user_and_data`` 2x sur le même user → ValueError."""
    user, _ = await _seed_user_with_jobs(db, storage, email="twice@gegm.local")

    await delete_user_and_data(
        db, user.id, actor_email=user.email, action=AuditAction.USER_SELF_DELETED, storage=storage
    )

    try:
        await delete_user_and_data(
            db,
            user.id,
            actor_email=user.email,
            action=AuditAction.USER_SELF_DELETED,
            storage=storage,
        )
    except ValueError as exc:
        assert "déjà supprimé" in str(exc).lower() or "introuvable" in str(exc).lower()
    else:
        raise AssertionError("ValueError attendue quand le user est déjà supprimé")


async def test_self_delete_endpoint_enqueues_task(client: AsyncClient) -> None:
    """``DELETE /api/users/me`` → 202 + task Celery enqueued."""
    # On mock ``delete_user_data_task.delay`` pour éviter de taper le broker Redis.
    with patch("app.users.router.delete_user_data_task.delay") as mock_delay:
        response = await client.delete("/api/users/me", headers=AUTH_HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    mock_delay.assert_called_once()
    kwargs = mock_delay.call_args.kwargs
    assert kwargs["actor_email"] == "pytest@test.local"
    assert kwargs["action"] == AuditAction.USER_SELF_DELETED.value


async def test_self_delete_requires_authentication(client: AsyncClient) -> None:
    """``DELETE /api/users/me`` sans token → 401."""
    response = await client.delete("/api/users/me")
    assert response.status_code == 401


async def test_admin_delete_rejects_non_admin(client: AsyncClient, monkeypatch: object) -> None:
    """``DELETE /api/admin/users/{id}`` → 403 si l'appelant n'est pas admin."""
    # Par défaut ADMIN_EMAILS est vide → 403 systématique.
    response = await client.delete(f"/api/admin/users/{uuid.uuid4()}", headers=AUTH_HEADERS)
    assert response.status_code == 403


async def test_admin_delete_returns_404_when_target_missing(
    client: AsyncClient, monkeypatch: object
) -> None:
    """``DELETE /api/admin/users/{id}`` → 404 si UUID absent."""
    # Autoriser pytest@test.local comme admin pour ce test uniquement.
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["pytest@test.local"])

    response = await client.delete(f"/api/admin/users/{uuid.uuid4()}", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_admin_delete_enqueues_task_for_existing_user(
    client: AsyncClient, db: AsyncSession, monkeypatch: object
) -> None:
    """Flow admin complet : cible existe, 202 + task enqueued avec admin_email."""
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["pytest@test.local"])

    # Seed une cible distincte du user admin courant.
    target = User(email="target@gegm.local", name="Cible")
    db.add(target)
    await db.commit()
    await db.refresh(target)

    with patch("app.users.router.delete_user_data_task.delay") as mock_delay:
        response = await client.delete(f"/api/admin/users/{target.id}", headers=AUTH_HEADERS)

    assert response.status_code == 202
    mock_delay.assert_called_once()
    kwargs = mock_delay.call_args.kwargs
    assert kwargs["actor_email"] == "pytest@test.local"
    assert kwargs["action"] == AuditAction.USER_ADMIN_DELETED.value
    assert kwargs["user_id"] == str(target.id)


async def test_get_or_create_excludes_soft_deleted(
    db: AsyncSession, storage: LocalStorageBackend
) -> None:
    """Un user purgé ne doit pas être "ressuscité" à la prochaine connexion."""
    user, _ = await _seed_user_with_jobs(db, storage, email="reborn@gegm.local")
    original_id = user.id

    await delete_user_and_data(
        db,
        user.id,
        actor_email=user.email,
        action=AuditAction.USER_SELF_DELETED,
        storage=storage,
    )

    # Re-login avec le même email → nouveau user avec nouvel UUID.
    fresh = await get_or_create_by_email(db, email="reborn@gegm.local", name="Renaissance")
    assert fresh.id != original_id
    assert fresh.deleted_at is None
