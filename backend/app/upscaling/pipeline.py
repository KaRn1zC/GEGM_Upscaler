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
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

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

    Guard CANCELLED : on relit ``job.status`` à deux moments :
    (1) en entrée d'étape — évite de lancer une inférence pour un job
        déjà annulé pendant sa file d'attente Celery,
    (2) juste avant le commit final (après download du résultat) — évite
        qu'un ``CANCELLED`` arrivé pendant l'inférence soit écrasé par
        l'écriture de ``output_key``.
    """
    from app.core.dependencies import get_storage
    from app.core.gpu.interface import UpscaleParams
    from app.jobs.models import Job, JobStatus

    storage = get_storage()
    redis = get_sync_redis()
    # Référence hors du try pour fermer le client HTTP du backend GPU dans
    # le finally (sinon le pool httpx fuit à chaque job).
    gpu: GPUBackend | None = None

    try:
        async with _open_db_session() as session:
            # Verrou de ligne (SELECT ... FOR UPDATE) : sérialise deux
            # exécutions concurrentes de cette tâche (cas résiduel de double
            # livraison broker). La seconde bloque jusqu'au commit de la
            # première, relit alors ``gpu_run_id`` déjà posé et se rattache
            # au run au lieu d'en soumettre un second. Le verrou est relâché
            # avant le polling (commit après la décision submit/rattach), pas
            # tenu pendant les minutes d'inférence.
            job = await session.get(Job, uuid.UUID(job_id), with_for_update=True)
            if job is None:
                raise ValueError(f"Job {job_id} introuvable en DB")

            if job.status == JobStatus.CANCELLED:
                logger.info(
                    "Job {jid} cancelled avant inférence — upscale skip",
                    jid=job_id,
                )
                return

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

            # Dims connues dès l'upload — servent au timeout dynamique et à
            # l'estimation de progression pendant l'inférence.
            input_mp = (job.input_width * job.input_height) / 1_000_000
            timeout_s = _compute_gpu_timeout(input_mp)

            # Reprise idempotente : si un run GPU est déjà rattaché à ce job
            # (message Celery rejoué — redelivery broker, double consommation
            # — ou retry après coupure réseau), on se rattache au run en
            # cours au lieu d'en soumettre et payer un deuxième. Observé en
            # prod le 2026-06-12 : 4 jobs GPU facturés pour un seul upscale.
            gpu_job_id: str | None = None
            if job.gpu_run_id:
                try:
                    existing = await gpu.get_job_status(job.gpu_run_id)
                except Exception as exc:
                    logger.warning(
                        "Run GPU existant {rid} injoignable ({err}) — resoumission",
                        rid=job.gpu_run_id,
                        err=str(exc),
                    )
                else:
                    if existing.status != GPUJobStatus.FAILED:
                        gpu_job_id = job.gpu_run_id
                        logger.info(
                            "Job {jid} : rattachement au run GPU actif {rid} (pas de resoumission)",
                            jid=job_id,
                            rid=gpu_job_id,
                        )

            if gpu_job_id is None:
                # Acheminement de l'image source vers le GPU. Deux modes :
                # - URL présignée (storage S3 + backend compatible) : le
                #   worker télécharge l'image lui-même — contourne la limite
                #   de payload RunPod (~7 Mo de fichier en base64) et épargne
                #   la RAM du worker Celery (aucun transit des bytes ici).
                # - Bytes inline (dev local, Core ML, rollback worker) :
                #   download puis base64.
                image_data: bytes | None = None
                image_url: str | None = None
                if (
                    gpu.supports_url_input
                    and settings.GPU_INPUT_URL_ENABLED
                    and settings.STORAGE_BACKEND == "s3"
                ):
                    # Expiration = timeout job + marge de queue : l'URL doit
                    # survivre au cold start + l'inférence, sans traîner des
                    # heures dans les logs RunPod (l'URL donne accès à l'input).
                    image_url = await storage.get_presigned_url(
                        job.input_key, expires_in=timeout_s + 900
                    )
                    # Le handler n'accepte que du HTTPS joignable depuis
                    # RunPod — un endpoint S3 interne (MinIO http) retombe
                    # en inline.
                    if not image_url.startswith("https://"):
                        logger.warning(
                            "URL présignée non-HTTPS ({url}) — fallback base64 inline",
                            url=image_url.split("?")[0],
                        )
                        image_url = None
                if image_url is None:
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
                gpu_job_id = await gpu.submit_job(
                    image_data,
                    params,
                    image_url=image_url,
                    execution_timeout_s=timeout_s,
                )

                # Persister le ``run_id`` GPU immédiatement pour que
                # ``cancel_job`` puisse le retrouver et appeler
                # ``RunPodBackend.cancel(run_id)`` upstream, et pour que
                # toute ré-exécution de cette tâche se rattache au run au
                # lieu de resoumettre. Ce commit relâche aussi le verrou de
                # ligne avant le polling.
                job.gpu_run_id = gpu_job_id
                await session.commit()
            else:
                # Rattachement : rien à écrire, mais on relâche le verrou de
                # ligne avant les minutes de polling.
                await session.commit()

            publish_progress_sync(
                redis, job_id, status="processing", progress=0.40, step="inference"
            )

            # Heartbeat : rafraîchit ``updated_at`` du job pour signaler au
            # reaper qu'un job long est vivant. UPDATE ciblé sur la seule
            # colonne ``updated_at`` — ne lit ni n'écrit ``status``, donc un
            # CANCELLED posé en parallèle par l'API n'est jamais écrasé.
            async def _touch_heartbeat() -> None:
                from sqlalchemy import func as sa_func
                from sqlalchemy import update as sa_update

                await session.execute(
                    sa_update(Job)
                    .where(Job.id == uuid.UUID(job_id))
                    .values(updated_at=sa_func.now())
                )
                await session.commit()

            # Polling jusqu'à completion — émet une progression continue
            # entre 0.40 et 0.70 pour que la barre frontend ne reste pas
            # figée pendant l'inférence RunPod, et heartbeat anti-reaper.
            result = await _wait_for_gpu_result(
                gpu,
                gpu_job_id,
                redis=redis,
                job_id=job_id,
                input_mp=input_mp,
                max_elapsed_s=float(timeout_s),
                on_heartbeat=_touch_heartbeat,
            )
            if result.status != GPUJobStatus.COMPLETED:
                raise RuntimeError(result.error or "Inférence GPU échouée")

            publish_progress_sync(redis, job_id, status="processing", progress=0.75, step="output")

            # Récupération du résultat (bytes ou flux disque) + upload
            # streamé vers le storage.
            output_data = _extract_output_bytes(gpu, gpu_job_id, result)
            if output_data is None:
                raise RuntimeError("Résultat GPU vide (output_data is None)")

            output_key = _build_output_key(job.input_key)
            try:
                await storage.upload(output_key, output_data, "image/png")
            finally:
                # Mode flux (gros output sur disque) : fermer le handle —
                # le fichier sous-jacent est nettoyé par gpu.close().
                if not isinstance(output_data, bytes):
                    output_data.close()

            # Re-check CANCELLED juste avant le commit final — un cancel
            # arrivé pendant l'inférence RunPod ne doit pas être écrasé
            # par l'écriture d'``output_key`` (ce qui ferait re-basculer
            # le job en flow ``completed``).
            await session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                logger.info(
                    "Job {jid} cancelled pendant inférence — output abandonné",
                    jid=job_id,
                )
                return

            # Persister output_key pour que ``_step_save`` finalise ensuite.
            job.output_key = output_key
            await session.commit()

        publish_progress_sync(redis, job_id, status="processing", progress=0.85, step="uploaded")
    finally:
        if gpu is not None:
            await gpu.close()
        redis.close()


async def _step_save(job_id: str) -> None:
    """Étape 5 — finalisation DB (statut COMPLETED, dimensions, completed_at).

    Incrémente aussi les compteurs Prometheus custom (jobs_total + duration)
    — la métrique est exposée via le serveur HTTP démarré par le worker.

    Guard CANCELLED : si le job a été annulé entre l'upscale et ce commit,
    on short-circuite — ``job.status`` reste à ``CANCELLED`` et les
    métriques ``completed`` ne sont pas incrémentées.
    """
    from app.jobs.models import Job, JobStatus

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")

        if job.status == JobStatus.CANCELLED:
            logger.info("Job {jid} cancelled — save skip", jid=job_id)
            return

        if job.output_key is None:
            # Normalement impossible si _step_upscale est allé jusqu'au bout,
            # sauf si ce dernier a bail out sur CANCELLED. Dans ce cas, on
            # ne doit pas avoir atteint _step_save (celery chain court-
            # circuitée), mais par sûreté on gère quand même.
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
    """Étape 6 — publication finale (``completed`` ou ``cancelled``) + cleanup Redis.

    Publie un event SSE distinct selon l'état final du job pour que le
    frontend puisse fermer le stream avec la bonne transition (évite
    d'afficher "completed" sur un job annulé en cours de route).
    """
    from app.jobs.models import Job, JobStatus

    async with _open_db_session() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} introuvable en DB")
        output_key = job.output_key
        final_status = job.status

    redis = get_sync_redis()
    try:
        if final_status == JobStatus.CANCELLED:
            publish_progress_sync(
                redis,
                job_id,
                status="cancelled",
                progress=0.0,
                step="cancelled",
            )
            logger.info("Job {jid} annulé — pipeline terminé proprement", jid=job_id)
        else:
            publish_progress_sync(
                redis,
                job_id,
                status="completed",
                progress=1.0,
                step="done",
                output_key=output_key,
            )
            logger.info("Job {jid} terminé avec succès", jid=job_id)
        cleanup_progress_sync(redis, job_id)
    finally:
        redis.close()


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


def _compute_gpu_timeout(input_mp: float) -> int:
    """Calcule le timeout d'un job GPU à partir de la taille de l'image.

    Durée estimée ``120 s + 200 s/MP`` (base = chargement modèle + warm-up
    cuDNN ; 200 s/MP recalibré sur DRCT-L x4 — ~37 s/tuile, ~5 tuiles/MP —
    mesuré sur RTX 5090 le 2026-06-17), avec un facteur 2 de marge, borné
    entre 10 minutes et ``settings.GPU_JOB_TIMEOUT_MAX_S``. La même valeur
    est transmise à RunPod (``policy.executionTimeout``) et sert de plafond
    de polling côté client — les deux bouts de la chaîne sont alignés.

    L'ancienne calibration (50 s/MP) sous-estimait d'un facteur ~4 le coût
    réel de DRCT-L x4 : un upscale de 12,5 MP coupé à mi-parcours faute de
    budget temps (cf. incident executionTimeout du 2026-06-17).

    Args:
        input_mp: Mégapixels de l'image source.

    Returns:
        Timeout en secondes.
    """
    estimated = 120.0 + 200.0 * input_mp
    return int(min(max(2.0 * estimated, 600.0), float(settings.GPU_JOB_TIMEOUT_MAX_S)))


async def _wait_for_gpu_result(
    gpu: GPUBackend,
    gpu_job_id: str,
    *,
    redis: object | None = None,
    job_id: str | None = None,
    input_mp: float = 1.0,
    max_elapsed_s: float = 600.0,
    on_heartbeat: Callable[[], Awaitable[None]] | None = None,
    heartbeat_interval_s: float = 60.0,
) -> GPUJobResult:
    """Poll le statut du job GPU jusqu'à complétion ou échec.

    Backoff exponentiel : 0.5s → 1s → 2s → 4s → 5s constant.
    Si le job reste en QUEUED plus de 30s (cold start RunPod détecté),
    le polling ralentit à 10s et le timeout s'étend de 5 minutes (le
    temps de queue n'est pas couvert par l'``executionTimeout`` RunPod,
    qui ne compte que l'exécution).

    Si ``redis`` et ``job_id`` sont fournis, émet une progression continue
    entre 0.40 et 0.70 à chaque polling tick (step "inference"). Ça évite
    que la barre frontend reste figée à 40 % pendant les 60-120 s
    d'inférence RunPod côté happy path. L'estimation utilise la formule
    ``60s de base + 50s/MP`` — conservatrice mais suffisante pour lisser
    l'UX : si l'inférence va plus vite, la barre sursaute à 0.75 quand
    l'output est téléchargé ; si elle traîne, la barre plafonne à 0.70.

    Args:
        gpu: Backend GPU qui a soumis le job.
        gpu_job_id: Identifiant retourné par ``submit_job``.
        redis: Instance Redis sync pour publier la progression (optionnel).
        job_id: UUID business du job, clé Redis (optionnel).
        input_mp: Mégapixels de l'image source, pour caler la durée estimée.
        max_elapsed_s: Plafond de polling en secondes — calculé par
            ``_compute_gpu_timeout`` selon la taille de l'image.
        on_heartbeat: Callback appelé toutes les ``heartbeat_interval_s``
            pendant le polling. Sert à rafraîchir l'``updated_at`` du job en
            base pour que le reaper ne fauche pas un job long mais bien
            vivant (cf. ``STALE_JOB_THRESHOLD_MINUTES``). Une exception du
            callback est loggée mais n'interrompt jamais le polling.
        heartbeat_interval_s: Cadence du heartbeat (60 s par défaut).

    Returns:
        ``GPUJobResult`` final.

    Raises:
        TimeoutError: Si le job ne se termine pas dans le délai imparti.
    """
    delays = [0.5, 1.0, 2.0, 4.0]
    # L'executionTimeout RunPod ne compte que l'exécution pure ; notre
    # polling compte queue + exécution + transferts S3 du handler. Marge
    # de 5 min d'office pour ne jamais abandonner un job que RunPod
    # laisserait légitimement finir.
    max_elapsed = max_elapsed_s + 300.0
    elapsed = 0.0
    last_heartbeat = 0.0
    cold_start_detected = False

    # Estimation de la durée d'inférence : 120s base + 200s par MP.
    # Recalibré sur DRCT-L x4 (RTX 5090, ~37s/tuile) — l'ancienne valeur
    # (50s/MP) figeait la barre à 70% pendant des dizaines de minutes.
    estimated_duration = max(60.0, 120.0 + 200.0 * input_mp)
    can_publish = redis is not None and job_id is not None

    while elapsed < max_elapsed:
        result = await gpu.get_job_status(gpu_job_id)

        if result.status in (GPUJobStatus.COMPLETED, GPUJobStatus.FAILED):
            return result

        # Cold start : le job reste en queue > 30s → adapter les paramètres.
        # +15 min de marge (pires cold starts RunPod observés, cf. seuil
        # STALE_JOB_THRESHOLD_MINUTES) — le temps de queue n'est pas
        # décompté par l'executionTimeout RunPod, mais il l'est par nous.
        if result.status == GPUJobStatus.QUEUED and elapsed > 30 and not cold_start_detected:
            cold_start_detected = True
            max_elapsed = max_elapsed_s + 900.0
            logger.info(
                "Cold start détecté pour job GPU {id} — timeout étendu à {t:.0f} min",
                id=gpu_job_id,
                t=max_elapsed / 60,
            )

        # Publication progressive entre 0.40 et 0.70 — linéaire sur la
        # durée estimée, plafonnée si l'inférence dépasse. Omet les tics
        # où on vient de publier la même valeur (évite de flooder Redis).
        if can_publish:
            fraction = min(elapsed / estimated_duration, 1.0)
            tick_progress = 0.40 + (0.70 - 0.40) * fraction
            publish_progress_sync(
                redis,  # type: ignore[arg-type]
                job_id,  # type: ignore[arg-type]
                status="processing",
                progress=round(tick_progress, 3),
                step="inference",
            )

        # Heartbeat anti-reaper : sur un job long (grosse image, plusieurs
        # heures), la progression part dans Redis mais l'``updated_at`` en
        # base ne bouge pas — le reaper le prendrait pour un zombie. On le
        # rafraîchit périodiquement. Une erreur ici ne doit jamais tuer le job.
        if on_heartbeat is not None and elapsed - last_heartbeat >= heartbeat_interval_s:
            try:
                await on_heartbeat()
            except Exception as exc:
                logger.warning(
                    "Heartbeat du job GPU {id} échoué : {err}",
                    id=gpu_job_id,
                    err=str(exc),
                )
            last_heartbeat = elapsed

        # Polling plus lent en cold start pour ne pas surcharger l'API RunPod.
        if cold_start_detected and result.status == GPUJobStatus.QUEUED:
            delay = 10.0
        elif elapsed < 10:
            delay = delays[min(int(elapsed // 2), len(delays) - 1)]
        else:
            delay = 5.0

        await asyncio.sleep(delay)
        elapsed += delay

    # Annuler côté provider avant d'abandonner : sans ça, le job RunPod
    # orphelin continue de tourner et de facturer (et un retry Celery en
    # resoumettrait un deuxième en parallèle).
    try:
        await gpu.cancel_job(gpu_job_id)
    except Exception as exc:
        logger.warning(
            "Annulation du job GPU {id} échouée après timeout : {err}",
            id=gpu_job_id,
            err=str(exc),
        )
    raise TimeoutError(f"Job GPU {gpu_job_id} n'a pas abouti en {max_elapsed / 60:.0f} minutes")


def _extract_output_bytes(
    gpu: GPUBackend, gpu_job_id: str, result: GPUJobResult
) -> bytes | BinaryIO | None:
    """Récupère le résultat via le backend GPU (bytes ou flux binaire).

    Core ML et le mode inline RunPod retournent des bytes en mémoire ;
    le mode S3 RunPod retourne un flux ouvert sur un fichier temporaire
    (les gros outputs sont streamés disque → storage sans pic RAM).

    Args:
        gpu: Backend GPU qui a traité le job.
        gpu_job_id: Identifiant du job GPU.
        result: ``GPUJobResult`` complété.

    Returns:
        Bytes ou flux binaire de l'image de sortie, ou ``None``.
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
