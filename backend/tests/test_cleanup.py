"""Tests de la tâche de nettoyage périodique ``jobs.cleanup_old_jobs``.

Ne teste pas le planning Celery Beat lui-même (intégration), mais la
logique de sélection des jobs éligibles et la suppression des fichiers.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.cleanup import cleanup_old_jobs
from app.jobs.models import Job, JobStatus
from app.users.models import User


async def _make_job(
    db: AsyncSession,
    *,
    user: User,
    status: JobStatus,
    age_days: int,
    input_key: str = "uploads/test.png",
    output_key: str | None = None,
) -> Job:
    """Helper : crée un job avec un ``created_at`` rétro-daté."""
    job = Job(
        user_id=user.id,
        status=status,
        input_key=input_key,
        output_key=output_key,
        scale_factor=4,
        model_name="drct-l",
        input_width=1000,
        input_height=1000,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Rétro-datage explicite après INSERT (``created_at`` a une valeur serveur).
    job.created_at = datetime.now(UTC) - timedelta(days=age_days)
    await db.commit()
    return job


def _mock_storage(*, missing: bool = False) -> AsyncMock:
    """Construit un mock du StorageBackend avec ``delete`` async."""
    storage = AsyncMock()
    if missing:
        storage.delete = AsyncMock(side_effect=FileNotFoundError("déjà absent"))
    else:
        storage.delete = AsyncMock(return_value=None)
    return storage


async def test_should_delete_old_completed_jobs(db: AsyncSession) -> None:
    """Un job COMPLETED plus vieux que ``retention_days`` doit être supprimé."""
    user = User(email="cleanup-test@gegm.local")
    db.add(user)
    await db.commit()
    old_job = await _make_job(db, user=user, status=JobStatus.COMPLETED, age_days=45)

    stats = await cleanup_old_jobs(db, retention_days=30, storage=_mock_storage())

    assert stats["jobs_deleted"] == 1

    result = await db.execute(select(Job).where(Job.id == old_job.id))
    assert result.scalar_one_or_none() is None


async def test_should_preserve_recent_jobs(db: AsyncSession) -> None:
    """Un job récent (< retention_days) ne doit pas être touché."""
    user = User(email="recent-test@gegm.local")
    db.add(user)
    await db.commit()
    recent = await _make_job(db, user=user, status=JobStatus.COMPLETED, age_days=5)

    stats = await cleanup_old_jobs(db, retention_days=30, storage=_mock_storage())

    assert stats["jobs_deleted"] == 0
    result = await db.execute(select(Job).where(Job.id == recent.id))
    assert result.scalar_one_or_none() is not None


async def test_should_preserve_active_jobs_even_if_old(db: AsyncSession) -> None:
    """Un job vieux mais toujours actif (processing) doit être préservé.

    Cas réel : job coincé en polling RunPod pendant une panne — on ne veut
    pas que le cleanup le tue.
    """
    user = User(email="stuck-test@gegm.local")
    db.add(user)
    await db.commit()
    stuck = await _make_job(db, user=user, status=JobStatus.PROCESSING, age_days=90)

    stats = await cleanup_old_jobs(db, retention_days=30, storage=_mock_storage())

    assert stats["jobs_deleted"] == 0
    result = await db.execute(select(Job).where(Job.id == stuck.id))
    assert result.scalar_one_or_none() is not None


async def test_should_delete_both_input_and_output_files(db: AsyncSession) -> None:
    """Un job avec input et output doit supprimer les 2 fichiers du storage."""
    user = User(email="dual-test@gegm.local")
    db.add(user)
    await db.commit()
    await _make_job(
        db,
        user=user,
        status=JobStatus.COMPLETED,
        age_days=60,
        input_key="uploads/old.png",
        output_key="results/old.png",
    )

    storage = _mock_storage()
    stats = await cleanup_old_jobs(db, retention_days=30, storage=storage)

    assert stats["files_deleted"] == 2
    storage.delete.assert_any_call("uploads/old.png")
    storage.delete.assert_any_call("results/old.png")


async def test_should_handle_missing_files_gracefully(db: AsyncSession) -> None:
    """Un fichier déjà supprimé (FileNotFoundError) ne doit pas bloquer le cleanup."""
    user = User(email="missing-file-test@gegm.local")
    db.add(user)
    await db.commit()
    old_job = await _make_job(
        db,
        user=user,
        status=JobStatus.COMPLETED,
        age_days=60,
        output_key="results/missing.png",
    )

    stats = await cleanup_old_jobs(db, retention_days=30, storage=_mock_storage(missing=True))

    # Le job doit quand même être supprimé, même si les fichiers sont absents.
    assert stats["jobs_deleted"] == 1
    assert stats["files_deleted"] == 0

    result = await db.execute(select(Job).where(Job.id == old_job.id))
    assert result.scalar_one_or_none() is None


async def test_should_skip_when_retention_zero_or_negative(db: AsyncSession) -> None:
    """``retention_days=0`` ou négatif → cleanup annulé, 0 job supprimé.

    Protection contre une config accidentelle qui supprimerait TOUS les jobs.
    """
    stats = await cleanup_old_jobs(db, retention_days=0, storage=_mock_storage())
    assert stats == {"jobs_deleted": 0, "files_deleted": 0}

    stats = await cleanup_old_jobs(db, retention_days=-5, storage=_mock_storage())
    assert stats == {"jobs_deleted": 0, "files_deleted": 0}
