"""Tâches Celery pour le pipeline d'upscaling.

En production, ce module contiendra le pipeline complet via Celery Canvas :
validate → preprocess → route_and_upscale → postprocess → save → notify.

Pour l'instant, une tâche mock simule le traitement sans GPU réel.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from loguru import logger

from app.core.celery import celery_app


@celery_app.task(bind=True, name="jobs.process_upscale")
def process_upscale(self: object, job_id: str) -> dict[str, str]:
    """Tâche mock d'upscaling — simule le traitement sans GPU.

    Crée un moteur DB dédié au worker (séparé du process API), met à
    jour le statut du job et simule une progression avec des pauses.

    Args:
        job_id: UUID du job à traiter (sérialisé en string par Celery).

    Returns:
        Dictionnaire avec le statut final et l'ID du job.
    """
    logger.info("Démarrage du job d'upscaling {job_id}", job_id=job_id)
    asyncio.run(_mock_process(job_id))
    return {"status": "completed", "job_id": job_id}


async def _mock_process(job_id: str) -> None:
    """Simule le traitement d'upscaling avec progression incrémentale.

    Utilise un moteur async dédié pour éviter le partage de pool de
    connexions avec le process API (event loops différentes).

    Args:
        job_id: UUID du job à traiter.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.jobs.models import Job, JobStatus

    # Moteur dédié au worker — pas de partage avec le process API.
    task_engine = create_async_engine(settings.DATABASE_URL)
    task_session_factory = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with task_session_factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if not job:
                logger.warning("Job {job_id} introuvable en DB", job_id=job_id)
                return

            job.status = JobStatus.PROCESSING
            job.gpu_backend = "mock"
            await session.commit()

            # Simulation de progression par paliers.
            for progress in (0.25, 0.5, 0.75, 1.0):
                await asyncio.sleep(0.5)
                job.progress = progress
                await session.commit()
                logger.debug(
                    "Job {job_id} — progression {pct}%",
                    job_id=job_id,
                    pct=int(progress * 100),
                )

            # Résultat mock : dimensions calculées, fichier simulé.
            job.status = JobStatus.COMPLETED
            job.output_key = job.input_key.replace("uploads/", "results/")
            job.output_width = job.input_width * job.scale_factor
            job.output_height = job.input_height * job.scale_factor
            job.completed_at = datetime.now(UTC)
            await session.commit()

            logger.info("Job {job_id} terminé avec succès", job_id=job_id)
    finally:
        await task_engine.dispose()
