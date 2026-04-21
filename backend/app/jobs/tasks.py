"""Tâches Celery pour le pipeline d'upscaling.

Ce module expose uniquement l'entry point Celery : le décorateur
``@celery_app.task`` avec sa configuration de retry. La logique métier
du pipeline est dans ``upscaling.pipeline.run_pipeline``.
"""

import asyncio

from loguru import logger

from app.core.celery import celery_app
from app.upscaling.pipeline import run_pipeline


@celery_app.task(
    bind=True,
    name="jobs.process_upscale",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def process_upscale(self: object, job_id: str) -> dict[str, str]:
    """Tâche Celery d'upscaling — point d'entrée du pipeline.

    Délègue toute la logique métier à ``upscaling.pipeline.run_pipeline``.
    Ce module ne contient que l'intégration Celery (retry, logging).

    Retry automatique avec backoff exponentiel sur erreurs réseau
    (``ConnectionError``, ``TimeoutError``, ``OSError``) — gère les cold
    starts RunPod et les coupures réseau transitoires.

    Args:
        job_id: UUID du job à traiter (sérialisé en string par Celery).

    Returns:
        Dictionnaire avec le statut final et l'ID du job.
    """
    logger.info(
        "Démarrage du job d'upscaling {job_id} (tentative {retry}/{max})",
        job_id=job_id,
        retry=self.request.retries,  # type: ignore[attr-defined]
        max=self.max_retries,  # type: ignore[attr-defined]
    )
    asyncio.run(run_pipeline(job_id))
    return {"status": "completed", "job_id": job_id}
