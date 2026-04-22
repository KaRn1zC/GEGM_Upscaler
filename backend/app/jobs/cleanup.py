"""Tâche Celery Beat de nettoyage périodique des jobs anciens.

Planifiée quotidiennement (cf. ``celery.py`` ``beat_schedule``), cette tâche
supprime les fichiers (inputs + outputs) et les enregistrements DB des jobs
plus anciens que ``settings.STORAGE_RETENTION_DAYS``. Évite que le storage
grossisse indéfiniment en production.

Politique de rétention : on supprime tous les jobs (completed, failed,
cancelled) dont ``created_at`` dépasse le seuil. Les jobs actifs (pending,
queued, processing) sont toujours préservés.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.celery import celery_app
from app.core.config import settings
from app.core.dependencies import get_storage

if TYPE_CHECKING:
    from app.jobs.models import Job


@celery_app.task(name="jobs.cleanup_old_jobs")
def cleanup_old_jobs_task() -> dict[str, int]:
    """Entry Celery — crée une session DB puis délègue à ``cleanup_old_jobs``.

    Returns:
        Statistiques ``{"jobs_deleted": N, "files_deleted": M}``.
    """
    logger.info(
        "Démarrage du nettoyage périodique (rétention {d} jours)",
        d=settings.STORAGE_RETENTION_DAYS,
    )
    return asyncio.run(_run_cleanup_task())


async def _run_cleanup_task() -> dict[str, int]:
    """Crée une session DB dédiée et appelle ``cleanup_old_jobs``.

    Returns:
        Statistiques ``{"jobs_deleted": N, "files_deleted": M}``.
    """
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    storage = get_storage()

    try:
        async with session_factory() as session:
            return await cleanup_old_jobs(session, settings.STORAGE_RETENTION_DAYS, storage=storage)
    finally:
        await engine.dispose()


async def cleanup_old_jobs(
    db: AsyncSession,
    retention_days: int,
    *,
    storage: object | None = None,
) -> dict[str, int]:
    """Supprime les jobs terminés plus anciens que ``retention_days``.

    Pour chaque job éligible :

    1. Suppression de l'input_key du storage (best-effort, log l'erreur).
    2. Suppression de l'output_key si présent (best-effort).
    3. Suppression de l'enregistrement DB.

    Les jobs actifs (pending, queued, processing) sont toujours préservés,
    même s'ils sont vieux : ils sont peut-être bloqués en retry ou en
    polling RunPod prolongé.

    Args:
        db: Session SQLAlchemy async (injectée pour faciliter les tests).
        retention_days: Âge maximal en jours. Doit être ≥ 1.
        storage: Instance ``StorageBackend``. Si ``None``, récupérée via
            ``get_storage()`` (utile en prod, overridé dans les tests).

    Returns:
        Dictionnaire ``{"jobs_deleted": N, "files_deleted": M}``.
    """
    if retention_days < 1:
        logger.warning("retention_days < 1, cleanup annulé")
        return {"jobs_deleted": 0, "files_deleted": 0}

    from app.jobs.models import Job, JobStatus

    storage = storage if storage is not None else get_storage()
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    terminal_statuses = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    result = await db.execute(
        select(Job).where(Job.created_at < cutoff, Job.status.in_(terminal_statuses))
    )
    old_jobs: list[Job] = list(result.scalars().all())

    logger.info(
        "{n} jobs anciens trouvés (seuil : {cutoff})",
        n=len(old_jobs),
        cutoff=cutoff.isoformat(),
    )

    jobs_deleted = 0
    files_deleted = 0
    for job in old_jobs:
        files_deleted += await _delete_job_files(storage, job)
        await db.delete(job)
        jobs_deleted += 1

    await db.commit()

    logger.info(
        "Cleanup terminé — {j} jobs supprimés, {f} fichiers nettoyés",
        j=jobs_deleted,
        f=files_deleted,
    )
    return {"jobs_deleted": jobs_deleted, "files_deleted": files_deleted}


async def _delete_job_files(storage: object, job: Job) -> int:
    """Supprime les fichiers input et output d'un job (best-effort).

    Les erreurs de suppression sont logguées mais n'interrompent pas le
    cleanup — il vaut mieux supprimer l'enregistrement DB que laisser un
    job fantôme à cause d'un fichier déjà absent côté storage.

    Args:
        storage: Instance ``StorageBackend``.
        job: Instance ``Job`` à nettoyer.

    Returns:
        Nombre de fichiers effectivement supprimés (0, 1 ou 2).
    """
    deleted = 0
    for key in (job.input_key, job.output_key):
        if not key:
            continue
        try:
            await storage.delete(key)  # type: ignore[attr-defined]
            deleted += 1
        except FileNotFoundError:
            # Fichier déjà absent — pas d'erreur, juste un warning.
            logger.debug("Fichier déjà absent : {k}", k=key)
        except Exception as exc:
            logger.warning(
                "Échec suppression fichier {k} (job {id}) : {err}",
                k=key,
                id=str(job.id),
                err=str(exc),
            )
    return deleted
