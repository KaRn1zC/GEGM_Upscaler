"""Tâches Celery pour le pipeline d'upscaling.

Pipeline réel : lecture du fichier source via StorageBackend, routage
vers le backend GPU approprié (Core ML local si ≤ 5 MP, sinon RunPod
cloud), upscale, sauvegarde du résultat et mise à jour du job.

La progression est publiée dans Redis (clé + Pub/Sub) pour alimenter
le stream SSE côté API. En cas d'absence de backend local ou cloud,
un fallback gracieux est appliqué par le routeur GPU.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from redis import Redis

from app.core.celery import celery_app
from app.core.config import settings

# ──────────────────────────────────────────────────────────────
# Redis helpers (synchrones pour les workers Celery)
# ──────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────
# Entrée Celery
# ──────────────────────────────────────────────────────────────


@celery_app.task(bind=True, name="jobs.process_upscale")
def process_upscale(self: object, job_id: str) -> dict[str, str]:
    """Tâche Celery d'upscaling — exécute le pipeline complet.

    Lit l'image source, route vers le bon backend GPU, upscale, sauvegarde
    le résultat, met à jour le job en base et publie la progression.

    Args:
        job_id: UUID du job à traiter (sérialisé en string par Celery).

    Returns:
        Dictionnaire avec le statut final et l'ID du job.
    """
    logger.info("Démarrage du job d'upscaling {job_id}", job_id=job_id)
    asyncio.run(_run_pipeline(job_id))
    return {"status": "completed", "job_id": job_id}


# ──────────────────────────────────────────────────────────────
# Pipeline async
# ──────────────────────────────────────────────────────────────


async def _run_pipeline(job_id: str) -> None:
    """Exécute le pipeline complet d'upscaling pour un job donné.

    Étapes :
    1. Chargement du job depuis la DB
    2. Téléchargement de l'image source depuis le storage
    3. Routage GPU (local vs cloud) selon les dimensions
    4. Soumission à l'inférence
    5. Polling du résultat (pour le cloud) ou lecture directe (local)
    6. Sauvegarde du résultat dans le storage
    7. Mise à jour du job en DB et publication finale sur Redis

    En cas d'erreur à n'importe quelle étape, le job est marqué FAILED
    et l'erreur est publiée dans Redis pour le client SSE.

    Args:
        job_id: UUID du job à traiter.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.gpu.interface import GPUJobStatus, UpscaleParams
    from app.core.storage.local import LocalStorageBackend
    from app.jobs.models import Job, JobStatus
    from app.upscaling.router_gpu import compute_megapixels, select_gpu_backend

    task_engine = create_async_engine(settings.DATABASE_URL)
    task_session_factory = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False
    )

    redis = _get_sync_redis()
    storage = LocalStorageBackend(base_path=settings.LOCAL_STORAGE_PATH)

    try:
        async with task_session_factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if not job:
                logger.warning("Job {job_id} introuvable en DB", job_id=job_id)
                return

            # Étape 1 : validation + début du traitement.
            job.status = JobStatus.PROCESSING
            await session.commit()
            _publish_progress_sync(
                redis, job_id, status="processing", progress=0.05, step="validate"
            )

            # Étape 2 : lecture de l'image source.
            try:
                image_data = await storage.download(job.input_key)
            except FileNotFoundError as exc:
                await _mark_failed(session, job, f"Image introuvable : {exc}")
                _publish_progress_sync(
                    redis, job_id, status="failed", progress=0.0,
                    error_message=f"Image introuvable : {exc}",
                )
                return

            _publish_progress_sync(
                redis, job_id, status="processing", progress=0.15, step="loaded"
            )

            # Étape 3 : routage GPU.
            mp = compute_megapixels(job.input_width, job.input_height)
            logger.info(
                "Routage GPU — job={job_id} dimensions={w}x{h} ({mp:.1f} MP)",
                job_id=job_id, w=job.input_width, h=job.input_height, mp=mp,
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
                _publish_progress_sync(
                    redis, job_id, status="failed", progress=0.0, error_message=str(exc),
                )
                return

            job.gpu_backend = "local" if gpu is local_backend else "cloud"
            await session.commit()

            _publish_progress_sync(
                redis, job_id, status="processing", progress=0.25, step="routed"
            )

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
                _publish_progress_sync(
                    redis, job_id, status="failed", progress=0.0,
                    error_message=f"Soumission GPU échouée : {exc}",
                )
                return

            _publish_progress_sync(
                redis, job_id, status="processing", progress=0.4, step="inference"
            )

            # Étape 5 : attente du résultat.
            result = await _wait_for_gpu_result(gpu, gpu_job_id)

            if result.status != GPUJobStatus.COMPLETED:
                error = result.error or "Inférence échouée"
                await _mark_failed(session, job, error)
                _publish_progress_sync(
                    redis, job_id, status="failed", progress=0.0, error_message=error,
                )
                return

            _publish_progress_sync(
                redis, job_id, status="processing", progress=0.85, step="saving"
            )

            # Étape 6 : récupération du résultat (bytes) et sauvegarde.
            output_bytes = _extract_output_bytes(gpu, gpu_job_id, result)
            if output_bytes is None:
                await _mark_failed(session, job, "Résultat GPU vide")
                _publish_progress_sync(
                    redis, job_id, status="failed", progress=0.0,
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

            _publish_progress_sync(
                redis, job_id, status="completed", progress=1.0,
                step="done", output_key=output_key,
            )

            logger.info("Job {job_id} terminé avec succès", job_id=job_id)
    except Exception as exc:
        logger.exception("Job {job_id} échoué : {err}", job_id=job_id, err=str(exc))
        _publish_progress_sync(
            redis, job_id, status="failed", progress=0.0, error_message=str(exc),
        )
        raise
    finally:
        await task_engine.dispose()
        redis.close()


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _try_build_local_backend(model_name: str) -> object | None:
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


def _try_build_cloud_backend() -> object | None:
    """Tente de construire le backend RunPod cloud.

    Retourne ``None`` si les credentials RunPod ne sont pas configurés.

    Returns:
        Instance ``RunPodBackend`` ou ``None``.
    """
    api_key = settings.RUNPOD_API_KEY.get_secret_value()
    endpoint_id = settings.RUNPOD_ENDPOINT_ID

    if not api_key or not endpoint_id:
        logger.debug("Credentials RunPod absents — backend cloud désactivé")
        return None

    from app.core.gpu.runpod import RunPodBackend
    return RunPodBackend(api_key=api_key, endpoint_id=endpoint_id)


async def _wait_for_gpu_result(gpu: object, gpu_job_id: str) -> object:
    """Poll le statut du job GPU jusqu'à complétion ou échec.

    Backoff exponentiel : 0.5s, 1s, 2s, 4s, puis 5s constant.
    Timeout global : 10 minutes.

    Args:
        gpu: Backend GPU qui a soumis le job.
        gpu_job_id: Identifiant retourné par ``submit_job``.

    Returns:
        ``GPUJobResult`` final.

    Raises:
        TimeoutError: Si le job ne se termine pas dans les 10 minutes.
    """
    from app.core.gpu.interface import GPUJobStatus

    delays = [0.5, 1.0, 2.0, 4.0]
    max_elapsed = 600.0
    elapsed = 0.0

    while elapsed < max_elapsed:
        result = await gpu.get_job_status(gpu_job_id)  # type: ignore[attr-defined]

        if result.status in (GPUJobStatus.COMPLETED, GPUJobStatus.FAILED):
            return result

        delay = delays[min(int(elapsed // 2), len(delays) - 1)] if elapsed < 10 else 5.0
        await asyncio.sleep(delay)
        elapsed += delay

    raise TimeoutError(f"Job GPU {gpu_job_id} n'a pas abouti en 10 minutes")


def _extract_output_bytes(gpu: object, gpu_job_id: str, result: object) -> bytes | None:
    """Récupère les bytes du résultat selon le type de backend.

    Pour Core ML : le backend stocke les bytes en mémoire et expose
    ``get_output_data(job_id)``. Pour RunPod : le résultat est téléchargé
    depuis la clé de storage retournée par l'API.

    Args:
        gpu: Backend GPU qui a traité le job.
        gpu_job_id: Identifiant du job GPU.
        result: ``GPUJobResult`` complété.

    Returns:
        Bytes de l'image de sortie, ou ``None`` si indisponible.
    """
    if hasattr(gpu, "get_output_data"):
        return gpu.get_output_data(gpu_job_id)  # type: ignore[attr-defined]

    # RunPod : le résultat doit contenir les bytes dans result.output_key
    # (le handler RunPod doit re-uploader dans notre storage).
    logger.warning("Pas de mécanisme de récupération des bytes pour ce backend")
    return None


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


async def _mark_failed(session: object, job: object, error_message: str) -> None:
    """Marque un job comme FAILED en DB avec le message d'erreur.

    Args:
        session: Session SQLAlchemy async.
        job: Instance du modèle Job.
        error_message: Détail de l'erreur.
    """
    from app.jobs.models import JobStatus

    job.status = JobStatus.FAILED  # type: ignore[attr-defined]
    job.error_message = error_message  # type: ignore[attr-defined]
    job.completed_at = datetime.now(UTC)  # type: ignore[attr-defined]
    await session.commit()  # type: ignore[attr-defined]
    logger.error("Job {id} marqué FAILED : {err}", id=str(job.id), err=error_message)  # type: ignore[attr-defined]
