"""Tâches Celery pour le pipeline d'upscaling.

En production, ce module contiendra le pipeline complet via Celery Canvas :
validate → preprocess → route_and_upscale → postprocess → save → notify.

Pour l'instant, une tâche mock simule le traitement sans GPU réel.
La progression est publiée dans Redis (clé + Pub/Sub) pour alimenter
le stream SSE côté API.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from loguru import logger
from redis import Redis

from app.core.celery import celery_app
from app.core.config import settings


def _get_sync_redis() -> Redis:
    """Crée un client Redis synchrone pour le worker Celery.

    Les workers Celery tournent dans des threads synchrones — on ne peut
    pas réutiliser le pool async de l'API. Le client est créé à chaque
    tâche pour éviter les problèmes de partage entre workers.

    Returns:
        Client ``redis.Redis`` synchrone.
    """
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _publish_progress_sync(
    redis: Redis,
    job_id: str,
    *,
    status: str,
    progress: float,
    step: str | None = None,
    output_key: str | None = None,
    error_message: str | None = None,
) -> None:
    """Publie la progression dans Redis de manière synchrone.

    Version synchrone de ``progress.publish_progress``, adaptée au
    contexte des workers Celery.

    Args:
        redis: Client Redis synchrone.
        job_id: UUID du job.
        status: Statut courant du job.
        progress: Avancement de 0.0 à 1.0.
        step: Étape courante du pipeline.
        output_key: Clé du résultat (fin de traitement).
        error_message: Détail de l'erreur éventuelle.
    """
    import json

    payload: dict[str, object] = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
    }
    if step is not None:
        payload["step"] = step
    if output_key is not None:
        payload["output_key"] = output_key
    if error_message is not None:
        payload["error_message"] = error_message

    encoded = json.dumps(payload)
    pipe = redis.pipeline(transaction=True)
    pipe.set(f"job:{job_id}:progress", encoded, ex=3600)
    pipe.publish(f"job:{job_id}:events", encoded)
    pipe.execute()


@celery_app.task(bind=True, name="jobs.process_upscale")
def process_upscale(self: object, job_id: str) -> dict[str, str]:
    """Tâche mock d'upscaling — simule le traitement sans GPU.

    Crée un moteur DB dédié au worker (séparé du process API), met à
    jour le statut du job et simule une progression avec des pauses.
    La progression est publiée dans Redis pour le stream SSE.

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

    Utilise un moteur async dédié pour la DB et un client Redis synchrone
    pour la publication de progression.

    Args:
        job_id: UUID du job à traiter.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.jobs.models import Job, JobStatus

    # Moteur dédié au worker — pas de partage avec le process API.
    task_engine = create_async_engine(settings.DATABASE_URL)
    task_session_factory = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False
    )

    redis = _get_sync_redis()

    try:
        async with task_session_factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if not job:
                logger.warning("Job {job_id} introuvable en DB", job_id=job_id)
                return

            job.status = JobStatus.PROCESSING
            job.gpu_backend = "mock"
            await session.commit()

            # Étapes simulées du pipeline.
            steps = [
                ("validate", 0.1),
                ("preprocess", 0.25),
                ("upscale", 0.5),
                ("upscale", 0.75),
                ("postprocess", 0.9),
            ]

            for step_name, progress_value in steps:
                await asyncio.sleep(0.5)
                job.progress = progress_value
                await session.commit()

                _publish_progress_sync(
                    redis,
                    job_id,
                    status="processing",
                    progress=progress_value,
                    step=step_name,
                )

                logger.debug(
                    "Job {job_id} — {step} {pct}%",
                    job_id=job_id,
                    step=step_name,
                    pct=int(progress_value * 100),
                )

            # Résultat mock : dimensions calculées, fichier simulé.
            output_key = job.input_key.replace("uploads/", "results/")
            job.status = JobStatus.COMPLETED
            job.output_key = output_key
            job.output_width = job.input_width * job.scale_factor
            job.output_height = job.input_height * job.scale_factor
            job.progress = 1.0
            job.completed_at = datetime.now(UTC)
            await session.commit()

            _publish_progress_sync(
                redis,
                job_id,
                status="completed",
                progress=1.0,
                step="done",
                output_key=output_key,
            )

            logger.info("Job {job_id} terminé avec succès", job_id=job_id)
    except Exception as exc:
        # Publier l'erreur dans Redis pour que le client SSE soit notifié.
        _publish_progress_sync(
            redis,
            job_id,
            status="failed",
            progress=0.0,
            error_message=str(exc),
        )
        logger.error("Job {job_id} échoué : {err}", job_id=job_id, err=str(exc))
        raise
    finally:
        await task_engine.dispose()
        redis.close()
