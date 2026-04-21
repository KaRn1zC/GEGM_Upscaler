"""Orchestration du pipeline d'upscaling.

Ce module contient la logique métier du pipeline — lecture DB, routage
GPU (Core ML local vs RunPod cloud), inférence, sauvegarde du résultat,
publication de progression. Il est invoqué par la tâche Celery
``process_upscale`` dans ``jobs.tasks`` via ``run_pipeline(job_id)``.

Séparation des responsabilités :

- ``jobs.tasks`` : entry point Celery (décorateur, retry, logging).
- ``upscaling.pipeline`` (ce module) : orchestration métier.
- ``upscaling.router_gpu`` : décision de routage (local vs cloud).
- ``jobs.progress_sync`` : helpers Redis pour publier la progression.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.core.config import settings
from app.core.gpu.interface import GPUBackend, GPUJobResult, GPUJobStatus
from app.jobs.progress_sync import (
    cleanup_progress_sync,
    get_sync_redis,
    publish_progress_sync,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.jobs.models import Job


async def run_pipeline(job_id: str) -> None:
    """Exécute le pipeline complet d'upscaling pour un job donné.

    Étapes :

    1. Chargement du job depuis la DB
    2. Téléchargement de l'image source depuis le storage
    3. Routage GPU (local vs cloud) selon les dimensions
    4. Soumission à l'inférence
    5. Polling du résultat (cloud) ou lecture directe (local)
    6. Sauvegarde du résultat dans le storage
    7. Mise à jour du job en DB et publication finale sur Redis

    En cas d'erreur à n'importe quelle étape, le job est marqué FAILED
    et l'erreur est publiée dans Redis pour le client SSE.

    Args:
        job_id: UUID du job à traiter (sous forme de string).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.dependencies import get_storage
    from app.core.gpu.interface import UpscaleParams
    from app.jobs.models import Job, JobStatus
    from app.upscaling.router_gpu import compute_megapixels, select_gpu_backend

    task_engine = create_async_engine(settings.DATABASE_URL)
    task_session_factory = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False
    )

    redis = get_sync_redis()
    # Utilise le backend configuré dans .env (local ou S3) — même logique que l'API.
    storage = get_storage()

    try:
        async with task_session_factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if not job:
                logger.warning("Job {job_id} introuvable en DB", job_id=job_id)
                return

            # Étape 1 : validation + début du traitement.
            job.status = JobStatus.PROCESSING
            await session.commit()
            publish_progress_sync(
                redis, job_id, status="processing", progress=0.05, step="validate"
            )

            # Étape 2 : lecture de l'image source.
            try:
                image_data = await storage.download(job.input_key)
            except FileNotFoundError as exc:
                await _mark_failed(session, job, f"Image introuvable : {exc}")
                publish_progress_sync(
                    redis,
                    job_id,
                    status="failed",
                    progress=0.0,
                    error_message=f"Image introuvable : {exc}",
                )
                return

            publish_progress_sync(redis, job_id, status="processing", progress=0.15, step="loaded")

            # Étape 3 : routage GPU.
            mp = compute_megapixels(job.input_width, job.input_height)
            logger.info(
                "Routage GPU — job={job_id} dimensions={w}x{h} ({mp:.1f} MP)",
                job_id=job_id,
                w=job.input_width,
                h=job.input_height,
                mp=mp,
            )

            local_backend = _try_build_local_backend(job.model_name)
            cloud_backend = _try_build_cloud_backend()

            try:
                gpu = select_gpu_backend(
                    job.input_width,
                    job.input_height,
                    local_backend=local_backend,
                    cloud_backend=cloud_backend,
                )
            except RuntimeError as exc:
                await _mark_failed(session, job, str(exc))
                publish_progress_sync(
                    redis,
                    job_id,
                    status="failed",
                    progress=0.0,
                    error_message=str(exc),
                )
                return

            job.gpu_backend = "local" if gpu is local_backend else "cloud"
            await session.commit()

            publish_progress_sync(redis, job_id, status="processing", progress=0.25, step="routed")

            # Étape 4 : soumission à l'inférence.
            params = UpscaleParams(
                scale_factor=job.scale_factor,
                model_name=job.model_name,
                output_format="png",
            )

            try:
                gpu_job_id = await gpu.submit_job(image_data, params)
            except Exception as exc:
                await _mark_failed(session, job, f"Soumission GPU échouée : {exc}")
                publish_progress_sync(
                    redis,
                    job_id,
                    status="failed",
                    progress=0.0,
                    error_message=f"Soumission GPU échouée : {exc}",
                )
                return

            publish_progress_sync(
                redis, job_id, status="processing", progress=0.4, step="inference"
            )

            # Étape 5 : attente du résultat.
            result = await _wait_for_gpu_result(gpu, gpu_job_id)

            if result.status != GPUJobStatus.COMPLETED:
                error = result.error or "Inférence échouée"
                await _mark_failed(session, job, error)
                publish_progress_sync(
                    redis,
                    job_id,
                    status="failed",
                    progress=0.0,
                    error_message=error,
                )
                return

            publish_progress_sync(redis, job_id, status="processing", progress=0.85, step="saving")

            # Étape 6 : récupération du résultat (bytes) et sauvegarde.
            output_bytes = _extract_output_bytes(gpu, gpu_job_id, result)
            if output_bytes is None:
                await _mark_failed(session, job, "Résultat GPU vide")
                publish_progress_sync(
                    redis,
                    job_id,
                    status="failed",
                    progress=0.0,
                    error_message="Résultat GPU vide",
                )
                return

            output_key = _build_output_key(job.input_key)
            await storage.upload(output_key, output_bytes, "image/png")

            # Étape 7 : finalisation du job en DB.
            job.status = JobStatus.COMPLETED
            job.output_key = output_key
            job.output_width = job.input_width * job.scale_factor
            job.output_height = job.input_height * job.scale_factor
            job.progress = 1.0
            job.completed_at = datetime.now(UTC)
            await session.commit()

            publish_progress_sync(
                redis,
                job_id,
                status="completed",
                progress=1.0,
                step="done",
                output_key=output_key,
            )

            logger.info("Job {job_id} terminé avec succès", job_id=job_id)

            # Nettoyage explicite de la clé de progression Redis.
            cleanup_progress_sync(redis, job_id)
    except Exception as exc:
        logger.exception("Job {job_id} échoué : {err}", job_id=job_id, err=str(exc))
        publish_progress_sync(
            redis,
            job_id,
            status="failed",
            progress=0.0,
            error_message=str(exc),
        )
        cleanup_progress_sync(redis, job_id)
        raise
    finally:
        await task_engine.dispose()
        redis.close()


# ──────────────────────────────────────────────────────────────
# Helpers privés
# ──────────────────────────────────────────────────────────────


def _try_build_local_backend(model_name: str) -> GPUBackend | None:
    """Tente de construire le backend Core ML local.

    Retourne ``None`` si le fichier modèle n'existe pas ou si coremltools
    n'est pas installé (ex: environnement Linux sans Core ML).

    Args:
        model_name: Nom du modèle (drct-l, hat-l).

    Returns:
        Instance ``CoreMLBackend`` ou ``None``.
    """
    model_path = Path(settings.COREML_MODEL_DIR) / f"{model_name}.mlpackage"
    if not model_path.exists():
        logger.debug("Modèle Core ML absent : {p}", p=str(model_path))
        return None

    try:
        from app.core.gpu.local_coreml import CoreMLBackend

        return CoreMLBackend(model_path=str(model_path))
    except ImportError:
        logger.debug("coremltools non disponible — backend local désactivé")
        return None


def _try_build_cloud_backend() -> GPUBackend | None:
    """Tente de construire le backend RunPod cloud.

    Retourne ``None`` si les credentials RunPod ne sont pas configurés.
    La config S3_OUTPUT_* est optionnelle : si présente, le backend peut
    télécharger les outputs volumineux que le handler upload sur le bucket
    (mode S3) ; sinon il fallback sur les outputs inline base64.

    Returns:
        Instance ``RunPodBackend`` ou ``None``.
    """
    api_key = settings.RUNPOD_API_KEY.get_secret_value()
    endpoint_id = settings.RUNPOD_ENDPOINT_ID

    if not api_key or not endpoint_id:
        logger.debug("Credentials RunPod absents — backend cloud désactivé")
        return None

    from app.core.gpu.runpod import RunPodBackend

    return RunPodBackend(
        api_key=api_key,
        endpoint_id=endpoint_id,
        s3_endpoint_url=settings.S3_OUTPUT_ENDPOINT_URL,
        s3_bucket=settings.S3_OUTPUT_BUCKET,
        s3_access_key=settings.S3_OUTPUT_ACCESS_KEY.get_secret_value(),
        s3_secret_key=settings.S3_OUTPUT_SECRET_KEY.get_secret_value(),
        s3_region=settings.S3_OUTPUT_REGION,
    )


async def _wait_for_gpu_result(gpu: GPUBackend, gpu_job_id: str) -> GPUJobResult:
    """Poll le statut du job GPU jusqu'à complétion ou échec.

    Backoff exponentiel : 0.5s → 1s → 2s → 4s → 5s constant.
    Si le job reste en QUEUED plus de 30s (cold start RunPod détecté),
    le polling ralentit à 10s et le timeout s'étend à 15 minutes.

    Args:
        gpu: Backend GPU qui a soumis le job.
        gpu_job_id: Identifiant retourné par ``submit_job``.

    Returns:
        ``GPUJobResult`` final.

    Raises:
        TimeoutError: Si le job ne se termine pas dans le délai imparti.
    """
    delays = [0.5, 1.0, 2.0, 4.0]
    max_elapsed = 600.0  # 10 minutes par défaut
    elapsed = 0.0
    cold_start_detected = False

    while elapsed < max_elapsed:
        result = await gpu.get_job_status(gpu_job_id)

        if result.status in (GPUJobStatus.COMPLETED, GPUJobStatus.FAILED):
            return result

        # Cold start : le job reste en queue > 30s → adapter les paramètres.
        if result.status == GPUJobStatus.QUEUED and elapsed > 30 and not cold_start_detected:
            cold_start_detected = True
            max_elapsed = 900.0  # 15 minutes pour absorber le cold start
            logger.info(
                "Cold start détecté pour job GPU {id} — timeout étendu à 15 min",
                id=gpu_job_id,
            )

        # Polling plus lent en cold start pour ne pas surcharger l'API RunPod.
        if cold_start_detected and result.status == GPUJobStatus.QUEUED:
            delay = 10.0
        elif elapsed < 10:
            delay = delays[min(int(elapsed // 2), len(delays) - 1)]
        else:
            delay = 5.0

        await asyncio.sleep(delay)
        elapsed += delay

    raise TimeoutError(f"Job GPU {gpu_job_id} n'a pas abouti en {max_elapsed / 60:.0f} minutes")


def _extract_output_bytes(gpu: GPUBackend, gpu_job_id: str, result: GPUJobResult) -> bytes | None:
    """Récupère les bytes du résultat via le backend GPU.

    Les deux backends (Core ML et RunPod) stockent les bytes en mémoire
    après inférence et les exposent via ``get_output_data(job_id)``.

    Args:
        gpu: Backend GPU qui a traité le job.
        gpu_job_id: Identifiant du job GPU.
        result: ``GPUJobResult`` complété.

    Returns:
        Bytes de l'image de sortie, ou ``None`` si indisponible.
    """
    return gpu.get_output_data(gpu_job_id)


def _build_output_key(input_key: str) -> str:
    """Construit la clé de sortie à partir de la clé d'entrée.

    Args:
        input_key: Clé de l'image source (ex: ``uploads/abc.png``).

    Returns:
        Clé du résultat (ex: ``results/abc.png``).
    """
    if input_key.startswith("uploads/"):
        return input_key.replace("uploads/", "results/", 1)
    return f"results/{input_key}"


async def _mark_failed(session: AsyncSession, job: Job, error_message: str) -> None:
    """Marque un job comme FAILED en DB avec le message d'erreur.

    Args:
        session: Session SQLAlchemy async.
        job: Instance du modèle Job.
        error_message: Détail de l'erreur.
    """
    from app.jobs.models import JobStatus

    job.status = JobStatus.FAILED
    job.error_message = error_message
    job.completed_at = datetime.now(UTC)
    await session.commit()
    logger.error("Job {id} marqué FAILED : {err}", id=str(job.id), err=error_message)
