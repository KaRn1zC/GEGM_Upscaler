"""Orchestration du pipeline d'upscaling en Celery Canvas.

Découpe le traitement en 6 tâches chaînées via ``celery.chain`` :

1. ``task_validate``   — PENDING → PROCESSING + progress 0.05
2. ``task_preprocess`` — placeholder validation input + progress 0.15
3. ``task_route``      — décide local vs cloud, update ``job.gpu_backend``
4. ``task_upscale``    — soumission GPU + polling + extract + upload (heavy, retry)
5. ``task_save``       — finalisation DB (COMPLETED, dims, completed_at)
6. ``task_notify``     — progression 1.0 + cleanup Redis

Contrat entre tâches : chacune reçoit et retourne un ``job_id: str`` unique
(pas de state dict complexe — chaque tâche re-charge depuis la DB). Ça garde
la serialization JSON triviale et évite les dépendances implicites entre
tâches.

En cas d'échec d'une étape, ``on_pipeline_failure`` est appelée via le
callback ``link_error`` et marque le job FAILED en DB + publie l'erreur
sur Redis pour le client SSE.

Seule ``task_upscale`` a un retry automatique — c'est la seule étape à
faire des appels réseau intensifs (download/upload storage, API RunPod).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from celery import chain
from loguru import logger

from app.core.celery import celery_app
from app.core.config import settings
from app.core.gpu.interface import GPUBackend, GPUJobResult, GPUJobStatus
from app.core.metrics import upscale_duration_seconds, upscale_jobs_total
from app.jobs.progress_sync import (
    cleanup_progress_sync,
    get_sync_redis,
    publish_progress_sync,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.jobs.models import Job


# ──────────────────────────────────────────────────────────────
# Helper commun : session DB async avec cleanup
# ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def _open_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Ouvre une session SQLAlchemy async dédiée à une étape du pipeline.

    Chaque tâche Celery crée son propre engine (les workers ne peuvent pas
    partager un pool asyncio). L'engine est disposé en fin de contexte.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


# ──────────────────────────────────────────────────────────────
# Étapes async (logique métier de chaque task Celery)
# ──────────────────────────────────────────────────────────────


async def _step_validate(job_id: str) -> None:
    """Étape 1 — charge le job, transition PENDING → PROCESSING."""
    from app.jobs.models import Job, JobStatus

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")

        job.status = JobStatus.PROCESSING
        await session.commit()

    redis = get_sync_redis()
    try:
        publish_progress_sync(redis, job_id, status="processing", progress=0.05, step="validate")
    finally:
        redis.close()


async def _step_preprocess(job_id: str) -> None:
    """Étape 2 — placeholder pour de futures validations input (conversion de
    format, vérification qualité, dimensions, etc.). Actuellement ne fait
    qu'annoncer la progression.
    """
    redis = get_sync_redis()
    try:
        publish_progress_sync(redis, job_id, status="processing", progress=0.15, step="preprocess")
    finally:
        redis.close()


async def _step_route(job_id: str) -> None:
    """Étape 3 — route vers le GPU approprié (local vs cloud), update DB."""
    from app.jobs.models import Job
    from app.upscaling.router_gpu import compute_megapixels, select_gpu_backend

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")

        mp = compute_megapixels(job.input_width, job.input_height)
        logger.info(
            "Routage GPU — job={jid} dims={w}x{h} ({mp:.1f} MP)",
            jid=job_id,
            w=job.input_width,
            h=job.input_height,
            mp=mp,
        )

        local_backend = _try_build_local_backend(job.model_name)
        cloud_backend = _try_build_cloud_backend()
        gpu = select_gpu_backend(
            job.input_width,
            job.input_height,
            local_backend=local_backend,
            cloud_backend=cloud_backend,
            prefer_local=job.prefer_local,
        )

        job.gpu_backend = "local" if gpu is local_backend else "cloud"
        await session.commit()

    redis = get_sync_redis()
    try:
        publish_progress_sync(redis, job_id, status="processing", progress=0.25, step="route")
    finally:
        redis.close()


async def _step_upscale(job_id: str) -> None:
    """Étape 4 — inférence GPU complète (submit + poll + extract + upload).

    C'est la tâche lourde du pipeline (plusieurs minutes). Son retry Celery
    (``autoretry_for`` sur ``task_upscale``) couvre les erreurs réseau
    transitoires (ConnectionError, TimeoutError) typiques des cold starts
    RunPod ou coupures réseau ponctuelles.
    """
    from app.core.dependencies import get_storage
    from app.core.gpu.interface import UpscaleParams
    from app.jobs.models import Job

    storage = get_storage()
    redis = get_sync_redis()

    try:
        async with _open_db_session() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if job is None:
                raise ValueError(f"Job {job_id} introuvable en DB")

            # Re-construction du backend GPU choisi en étape 3.
            gpu = (
                _try_build_local_backend(job.model_name)
                if job.gpu_backend == "local"
                else _try_build_cloud_backend()
            )
            if gpu is None:
                raise RuntimeError(
                    f"Backend GPU '{job.gpu_backend}' indisponible au moment de l'upscale"
                )

            # Download de l'image source.
            image_data = await storage.download(job.input_key)
            publish_progress_sync(
                redis, job_id, status="processing", progress=0.30, step="downloaded"
            )

            # Soumission au GPU.
            params = UpscaleParams(
                scale_factor=job.scale_factor,
                model_name=job.model_name,
                output_format="png",
            )
            gpu_job_id = await gpu.submit_job(image_data, params)
            publish_progress_sync(
                redis, job_id, status="processing", progress=0.40, step="inference"
            )

            # Polling jusqu'à completion.
            result = await _wait_for_gpu_result(gpu, gpu_job_id)
            if result.status != GPUJobStatus.COMPLETED:
                raise RuntimeError(result.error or "Inférence GPU échouée")

            publish_progress_sync(redis, job_id, status="processing", progress=0.75, step="output")

            # Récupération des bytes + upload sur le storage.
            output_bytes = _extract_output_bytes(gpu, gpu_job_id, result)
            if output_bytes is None:
                raise RuntimeError("Résultat GPU vide (output_bytes is None)")

            output_key = _build_output_key(job.input_key)
            await storage.upload(output_key, output_bytes, "image/png")

            # Persister output_key pour que ``_step_save`` finalise ensuite.
            job.output_key = output_key
            await session.commit()

        publish_progress_sync(redis, job_id, status="processing", progress=0.85, step="uploaded")
    finally:
        redis.close()


async def _step_save(job_id: str) -> None:
    """Étape 5 — finalisation DB (statut COMPLETED, dimensions, completed_at).

    Incrémente aussi les compteurs Prometheus custom (jobs_total + duration)
    — la métrique est exposée via le serveur HTTP démarré par le worker.
    """
    from app.jobs.models import Job, JobStatus

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")
        if job.output_key is None:
            raise RuntimeError(f"Job {job_id} sans output_key au moment du save")

        job.status = JobStatus.COMPLETED
        job.output_width = job.input_width * job.scale_factor
        job.output_height = job.input_height * job.scale_factor
        job.progress = 1.0
        job.completed_at = datetime.now(UTC)
        await session.commit()

        # Instrumentation Prometheus — on lit les champs avant fermeture de session.
        backend = job.gpu_backend or "unknown"
        model = job.model_name or "unknown"
        duration = (job.completed_at - job.created_at).total_seconds()

    upscale_jobs_total.labels(status="completed", backend=backend, model=model).inc()
    upscale_duration_seconds.labels(backend=backend, model=model).observe(duration)

    redis = get_sync_redis()
    try:
        publish_progress_sync(redis, job_id, status="processing", progress=0.95, step="save")
    finally:
        redis.close()


async def _step_notify(job_id: str) -> None:
    """Étape 6 — publication finale ``completed`` + cleanup clé Redis."""
    from app.jobs.models import Job

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")
        output_key = job.output_key

    redis = get_sync_redis()
    try:
        publish_progress_sync(
            redis,
            job_id,
            status="completed",
            progress=1.0,
            step="done",
            output_key=output_key,
        )
        cleanup_progress_sync(redis, job_id)
    finally:
        redis.close()

    logger.info("Job {jid} terminé avec succès", jid=job_id)


# ──────────────────────────────────────────────────────────────
# Tâches Celery (wrappers sync sur les fonctions async ci-dessus)
# ──────────────────────────────────────────────────────────────


@celery_app.task(name="pipeline.validate")
def task_validate(job_id: str) -> str:
    """Tâche Celery — étape 1 (validate)."""
    asyncio.run(_step_validate(job_id))
    return job_id


@celery_app.task(name="pipeline.preprocess")
def task_preprocess(job_id: str) -> str:
    """Tâche Celery — étape 2 (preprocess)."""
    asyncio.run(_step_preprocess(job_id))
    return job_id


@celery_app.task(name="pipeline.route")
def task_route(job_id: str) -> str:
    """Tâche Celery — étape 3 (route)."""
    asyncio.run(_step_route(job_id))
    return job_id


@celery_app.task(
    name="pipeline.upscale",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def task_upscale(job_id: str) -> str:
    """Tâche Celery — étape 4 (upscale, avec retry réseau).

    Seule étape qui bénéficie du retry : elle fait tous les appels réseau
    intensifs (download/upload storage, API RunPod). Les autres étapes
    sont des ops locales DB/Redis qui ne devraient pas échouer en
    transitoire.
    """
    asyncio.run(_step_upscale(job_id))
    return job_id


@celery_app.task(name="pipeline.save")
def task_save(job_id: str) -> str:
    """Tâche Celery — étape 5 (save)."""
    asyncio.run(_step_save(job_id))
    return job_id


@celery_app.task(name="pipeline.notify")
def task_notify(job_id: str) -> str:
    """Tâche Celery — étape 6 (notify)."""
    asyncio.run(_step_notify(job_id))
    return job_id


# ──────────────────────────────────────────────────────────────
# Gestion d'erreur — callback ``link_error``
# ──────────────────────────────────────────────────────────────


@celery_app.task(name="pipeline.on_failure")
def on_pipeline_failure(
    task_id: str,
    exc: object,
    traceback: object,
    job_id: str,
) -> None:
    """Callback ``link_error`` — marque le job FAILED en cas d'échec de chain.

    Celery appelle cette tâche automatiquement si n'importe quelle étape
    de la chain raise une exception non rattrapée (après épuisement des
    retries éventuels).

    Args:
        task_id: ID Celery de la tâche qui a échoué (fourni par Celery).
        exc: Exception (fournie par Celery).
        traceback: Trace (fournie par Celery).
        job_id: UUID business du job, injecté via ``.s(job_id)`` dans
            ``run_pipeline_chain``.
    """
    logger.error(
        "Pipeline failure — task_id={tid} job_id={jid} exc={exc}",
        tid=task_id,
        jid=job_id,
        exc=str(exc),
    )
    asyncio.run(_handle_pipeline_failure(job_id, str(exc)))


async def _handle_pipeline_failure(job_id: str, error_message: str) -> None:
    """Met à jour la DB (job FAILED) + publie l'échec sur Redis.

    Idempotent : si le job est déjà dans un état terminal, ne fait rien
    (évite d'écraser un COMPLETED par un FAILED tardif).
    """
    from app.jobs.models import Job, JobStatus

    backend = "unknown"
    model = "unknown"
    marked_failed = False

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            logger.warning("Job {jid} introuvable lors du handle_failure", jid=job_id)
            return

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return  # Déjà terminal — on n'écrase pas.

        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        await session.commit()

        backend = job.gpu_backend or "unknown"
        model = job.model_name or "unknown"
        marked_failed = True

    # Instrumentation Prometheus — hors du bloc session pour éviter que la
    # métrique soit incrémentée si le commit échoue (rare mais possible).
    if marked_failed:
        upscale_jobs_total.labels(status="failed", backend=backend, model=model).inc()

    redis = get_sync_redis()
    try:
        publish_progress_sync(
            redis,
            job_id,
            status="failed",
            progress=0.0,
            error_message=error_message,
        )
        cleanup_progress_sync(redis, job_id)
    finally:
        redis.close()


# ──────────────────────────────────────────────────────────────
# Composition de la chain — entry point public
# ──────────────────────────────────────────────────────────────


def run_pipeline_chain(job_id: str) -> str:
    """Lance le pipeline complet en Celery Canvas chain.

    Compose les 6 tâches ``validate → preprocess → route → upscale → save
    → notify``. En cas d'échec à n'importe quelle étape (après retry
    éventuel), ``on_pipeline_failure`` est appelée et marque le job FAILED.

    Args:
        job_id: UUID du job à traiter.

    Returns:
        ID Celery de la tâche root (utile pour le tracking / Flower).
    """
    workflow = chain(
        task_validate.s(job_id),
        task_preprocess.s(),
        task_route.s(),
        task_upscale.s(),
        task_save.s(),
        task_notify.s(),
    )
    result = workflow.apply_async(link_error=on_pipeline_failure.s(job_id))
    logger.info(
        "Pipeline chain dispatched — job={jid} task_root={tid}",
        jid=job_id,
        tid=result.id,
    )
    root_id: str = result.id
    return root_id


# ──────────────────────────────────────────────────────────────
# Helpers privés (partagés entre les étapes)
# ──────────────────────────────────────────────────────────────


def _try_build_local_backend(model_name: str) -> GPUBackend | None:
    """Tente de construire le backend Core ML local.

    Retourne ``None`` si le fichier modèle n'existe pas ou si coremltools
    n'est pas installé (ex. environnement Linux sans Core ML).

    Args:
        model_name: Nom du modèle (``drct-l``, ``hat-l``).

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
    La config ``S3_OUTPUT_*`` est optionnelle : si présente, le backend peut
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
        input_key: Clé de l'image source (ex. ``uploads/abc.png``).

    Returns:
        Clé du résultat (ex. ``results/abc.png``).
    """
    if input_key.startswith("uploads/"):
        return input_key.replace("uploads/", "results/", 1)
    return f"results/{input_key}"


async def _mark_failed(session: AsyncSession, job: Job, error_message: str) -> None:
    """Marque un job comme FAILED en DB (utilitaire exposé pour tests legacy).

    Dans le pipeline Canvas, l'échec est géré par ``on_pipeline_failure``
    qui appelle ``_handle_pipeline_failure``. Cette fonction reste exposée
    pour compatibilité éventuelle et comme utilitaire générique.

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
