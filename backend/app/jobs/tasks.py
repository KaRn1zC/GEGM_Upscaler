"""Tâche Celery d'entrée du pipeline d'upscaling.

Ce module expose uniquement la tâche ``jobs.process_upscale`` qui
déclenche le pipeline composé en Celery Canvas (défini dans
``app.upscaling.pipeline``).

Les 6 étapes (validate → preprocess → route → upscale → save → notify)
sont indépendantes, chacune retry-able individuellement si besoin.
L'étape ``task_upscale`` a son propre retry automatique sur erreurs
réseau (RunPod cold starts, timeouts) — les autres étapes sont des
opérations locales qui n'en bénéficieraient pas.
"""

from loguru import logger

from app.core.celery import celery_app
from app.upscaling.pipeline import run_pipeline_chain


@celery_app.task(name="jobs.process_upscale")
def process_upscale(job_id: str) -> dict[str, str]:
    """Entry point Celery — déclenche le pipeline chain pour un job.

    Cette tâche se contente de dispatcher la chain et retourne immédiatement.
    Le vrai traitement se fait dans les 6 tâches chaînées de
    ``upscaling.pipeline``.

    Args:
        job_id: UUID du job à traiter (sérialisé en string par Celery).

    Returns:
        Dictionnaire avec le statut de dispatch et l'ID du job.
    """
    logger.info("Dispatch pipeline chain pour job {jid}", jid=job_id)
    root_task_id = run_pipeline_chain(job_id)
    return {"status": "dispatched", "job_id": job_id, "root_task_id": root_task_id}
