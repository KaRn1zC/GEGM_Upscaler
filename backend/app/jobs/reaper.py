"""Tâche Celery Beat de nettoyage des jobs zombies.

Un job zombie est un enregistrement en statut ``PROCESSING`` dont le champ
``updated_at`` n'a pas bougé depuis plus de ``STALE_JOB_THRESHOLD_MINUTES``.
Scénarios qui en génèrent :

- Crash silencieux d'un worker Celery entre deux commits DB (process killé,
  OOM, etc.) — la tâche n'atteint jamais ``_step_save``.
- Docker compose down sauvage pendant un pipeline en cours.
- Bug exceptionnel dans le pipeline qui se plante sans passer par
  ``on_pipeline_failure``.

Sans reaper, ces jobs restent ``PROCESSING`` indéfiniment et polluent
l'UI (progress bar figée, "en cours" éternel) tout en pouvant fausser
les métriques Prometheus.

La stratégie est de refléter la réalité : un job qui n'a pas avancé
depuis 30 min ne finira plus, on le marque ``FAILED`` avec un message
explicite. L'utilisateur peut alors le supprimer ou le relancer.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.celery import celery_app
from app.core.config import settings


@celery_app.task(name="jobs.reap_stale_jobs")
def reap_stale_jobs_task() -> dict[str, int]:
    """Entry Celery Beat — traite les jobs zombies.

    Returns:
        Statistiques ``{"reaped": N}`` — nombre de jobs passés en FAILED.
    """
    threshold = settings.STALE_JOB_THRESHOLD_MINUTES
    logger.debug("Reaper démarré (seuil : {m} min)", m=threshold)
    return asyncio.run(_run_reaper(threshold))


async def _run_reaper(threshold_minutes: int) -> dict[str, int]:
    """Ouvre une session DB et délègue à ``reap_stale_jobs``."""
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await reap_stale_jobs(session, threshold_minutes)
    finally:
        await engine.dispose()


async def reap_stale_jobs(db: AsyncSession, threshold_minutes: int) -> dict[str, int]:
    """Marque FAILED les jobs PROCESSING sans update depuis le seuil.

    Opère par UPDATE bulk pour éviter les aller-retours N+1 si plusieurs
    zombies sont détectés. Idempotent : une ré-exécution immédiate ne
    re-marquera rien (les jobs sont déjà en FAILED).

    Args:
        db: Session SQLAlchemy async (injectée pour faciliter les tests).
        threshold_minutes: Âge minimal d'un job sans update pour le
            considérer zombie. Doit être ≥ 1.

    Returns:
        Dictionnaire ``{"reaped": N}`` — N = nombre de rows mises à jour.
    """
    if threshold_minutes < 1:
        logger.warning("threshold_minutes < 1, reaper annulé")
        return {"reaped": 0}

    from app.jobs.models import Job, JobStatus

    cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)

    # Listing pour les logs (avant l'UPDATE bulk) — utile pour debug.
    result = await db.execute(
        select(Job.id).where(
            Job.status == JobStatus.PROCESSING,
            Job.updated_at < cutoff,
        )
    )
    stale_ids = [row[0] for row in result.all()]

    if not stale_ids:
        return {"reaped": 0}

    error_message = (
        f"Job zombie — aucune mise à jour depuis plus de {threshold_minutes} minutes. "
        f"Le worker a probablement crashé pendant le traitement."
    )

    await db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.PROCESSING,
            Job.updated_at < cutoff,
        )
        .values(
            status=JobStatus.FAILED,
            error_message=error_message,
            completed_at=datetime.now(UTC),
        )
    )
    await db.commit()

    logger.warning(
        "Reaper — {n} jobs zombies marqués FAILED (ids : {ids})",
        n=len(stale_ids),
        ids=", ".join(str(jid) for jid in stale_ids),
    )
    return {"reaped": len(stale_ids)}
