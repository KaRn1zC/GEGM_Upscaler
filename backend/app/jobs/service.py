"""Logique métier pour la gestion des jobs d'upscaling.

Création, lecture, listing et annulation des jobs. La création
dispatche automatiquement une tâche Celery pour le traitement.
"""

import uuid
from io import BytesIO

from fastapi import HTTPException
from loguru import logger
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage.interface import StorageBackend
from app.jobs.models import Job, JobStatus
from app.jobs.schemas import JobCreate
from app.users.models import User

# Mapping scale_factor → modèle SR. Seuls ces couples (modèle, scale) ont
# des poids pré-entraînés publics et sont supportés par le worker RunPod.
# - DRCT-L x4 : poids `drct-l_x4.pth` (ming053l/DRCT, ~486 MB)
# - HAT-L  x2 : poids `hat-l_x2.pth`  (XPixelGroup/HAT, ~165 MB)
_SCALE_TO_MODEL: dict[int, str] = {2: "hat-l", 4: "drct-l"}


def _model_for_scale(scale_factor: int) -> str:
    """Retourne le nom du modèle SR à utiliser pour un ``scale_factor`` donné.

    Raises:
        ValueError: si le facteur n'a pas de modèle associé.
    """
    try:
        return _SCALE_TO_MODEL[scale_factor]
    except KeyError as exc:
        raise ValueError(
            f"scale_factor {scale_factor} non supporté — "
            f"valeurs valides : {sorted(_SCALE_TO_MODEL.keys())}"
        ) from exc


async def create_job(
    payload: JobCreate,
    user: User,
    db: AsyncSession,
    storage: StorageBackend,
) -> Job:
    """Crée un job d'upscaling et dispatche la tâche Celery.

    Télécharge l'image source depuis le stockage pour en extraire les
    dimensions, crée l'enregistrement en base, puis envoie la tâche
    au worker Celery.

    Args:
        payload: Paramètres du job (clé source, facteur, modèle).
        user: Utilisateur authentifié propriétaire du job.
        db: Session de base de données.
        storage: Backend de stockage pour accéder à l'image source.

    Returns:
        Le job créé avec ses métadonnées complètes.

    Raises:
        HTTPException: 404 si l'image source n'existe pas dans le stockage.
        HTTPException: 400 si l'image source est illisible.
    """
    try:
        image_data = await storage.download(payload.input_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Fichier introuvable : {payload.input_key}",
        ) from exc

    try:
        img = Image.open(BytesIO(image_data))
        width, height = img.size
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Impossible de lire l'image source",
        ) from exc

    # Routage scale → modèle : chaque scale_factor a son modèle natif
    # dédié (seuls les poids pré-entraînés existants sont utilisés).
    # - x4 → DRCT-L (state-of-the-art, poids officiels ming053l/DRCT)
    # - x2 → HAT-L  (poids officiels XPixelGroup/HAT ; DRCT-L x2 non publié)
    # Tout ``model_name`` fourni par le client est ignoré — le serveur
    # est la source de vérité pour éviter les combinaisons non supportées.
    model_name = _model_for_scale(payload.scale_factor)

    job = Job(
        user_id=user.id,
        status=JobStatus.PENDING,
        input_key=payload.input_key,
        scale_factor=payload.scale_factor,
        model_name=model_name,
        input_width=width,
        input_height=height,
        prefer_local=payload.prefer_local,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Import tardif pour éviter les imports circulaires avec Celery.
    from app.jobs.tasks import process_upscale

    process_upscale.delay(str(job.id))

    return job


async def list_user_jobs(user: User, db: AsyncSession) -> list[Job]:
    """Retourne tous les jobs de l'utilisateur, du plus récent au plus ancien.

    Args:
        user: Utilisateur dont on veut les jobs.
        db: Session de base de données.

    Returns:
        Liste des jobs triés par date de création décroissante.
    """
    result = await db.execute(
        select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())
    )
    return list(result.scalars().all())


async def get_job(job_id: uuid.UUID, user: User, db: AsyncSession) -> Job:
    """Retourne un job par son ID, en vérifiant qu'il appartient à l'utilisateur.

    Args:
        job_id: Identifiant UUID du job.
        user: Utilisateur authentifié (pour vérification de propriété).
        db: Session de base de données.

    Returns:
        Le job correspondant.

    Raises:
        HTTPException: 404 si le job n'existe pas ou n'appartient pas à l'utilisateur.
    """
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return job


async def cancel_job(job_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    """Annule un job dans un état non-terminal (pending, queued, processing).

    Couvre aussi l'abandon d'un job en cours : utile pour stopper un upscale
    déjà long (cold-start RunPod prolongé) ou purger un orphelin laissé
    par une crash précédente du worker. Si le job tournait sur RunPod (cloud),
    un cancel upstream est envoyé pour stopper la facturation serverless.

    Note : la protection côté pipeline contre l'écrasement de ``CANCELLED``
    par un ``COMPLETED`` tardif est gérée par les guards dans
    ``upscaling/pipeline.py`` (H.2-bis : guard CANCELLED).

    Args:
        job_id: Identifiant UUID du job à annuler.
        user: Utilisateur authentifié (pour vérification de propriété).
        db: Session de base de données.

    Raises:
        HTTPException: 404 si le job n'existe pas.
        HTTPException: 409 si le job est déjà dans un état terminal
            (completed, failed, cancelled).
    """
    job = await get_job(job_id, user, db)

    non_cancellable = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    if job.status in non_cancellable:
        raise HTTPException(
            status_code=409,
            detail=f"Impossible d'annuler un job en statut '{job.status}'",
        )

    # Snapshot des champs utiles avant de modifier l'état en DB — on les
    # utilisera juste après pour l'éventuel cancel upstream RunPod.
    gpu_backend = job.gpu_backend
    gpu_run_id = job.gpu_run_id

    job.status = JobStatus.CANCELLED
    await db.commit()

    # Cancel upstream RunPod — best-effort, ne fait pas planter le cancel
    # côté app si RunPod est temporairement indispo. Sans ça, RunPod
    # continuerait l'inférence jusqu'à completion et facturerait pour rien.
    if gpu_backend == "cloud" and gpu_run_id:
        await _cancel_runpod_upstream(gpu_run_id)


async def _cancel_runpod_upstream(gpu_run_id: str) -> None:
    """Appelle RunPod pour annuler un job serverless en cours.

    Construit un ``RunPodBackend`` uniquement pour cette opération (léger,
    pas besoin de singleton). Les erreurs sont loggées mais non propagées —
    le cancel côté app doit toujours réussir même si RunPod est down.

    Args:
        gpu_run_id: Identifiant du job côté RunPod.
    """
    api_key = settings.RUNPOD_API_KEY.get_secret_value()
    endpoint_id = settings.RUNPOD_ENDPOINT_ID
    if not api_key or not endpoint_id:
        logger.warning(
            "Cancel upstream impossible — creds RunPod absents (run_id={rid})",
            rid=gpu_run_id,
        )
        return

    from app.core.gpu.runpod import RunPodBackend

    backend = RunPodBackend(
        api_key=api_key,
        endpoint_id=endpoint_id,
        s3_endpoint_url=settings.S3_OUTPUT_ENDPOINT_URL,
        s3_bucket=settings.S3_OUTPUT_BUCKET,
        s3_access_key=settings.S3_OUTPUT_ACCESS_KEY.get_secret_value(),
        s3_secret_key=settings.S3_OUTPUT_SECRET_KEY.get_secret_value(),
        s3_region=settings.S3_OUTPUT_REGION,
    )
    try:
        await backend.cancel_job(gpu_run_id)
        logger.info("Cancel upstream RunPod envoyé — run_id={rid}", rid=gpu_run_id)
    except Exception as exc:
        # Best-effort : on log mais on ne propage pas. Le reaper et/ou
        # l'idle timeout RunPod finiront par nettoyer.
        logger.warning(
            "Cancel upstream RunPod échoué — run_id={rid} err={err}",
            rid=gpu_run_id,
            err=str(exc),
        )
    finally:
        await backend.close()
