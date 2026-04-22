"""Logique métier pour la gestion des jobs d'upscaling.

Création, lecture, listing et annulation des jobs. La création
dispatche automatiquement une tâche Celery pour le traitement.
"""

import uuid
from io import BytesIO

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage.interface import StorageBackend
from app.jobs.models import Job, JobStatus
from app.jobs.schemas import JobCreate
from app.users.models import User


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

    model_name = payload.model_name or settings.UPSCALE_MODEL

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
    par une crash précédente du worker.

    Note : en cas d'annulation pendant `processing`, le pipeline Celery
    continue son exécution RunPod. Pour que la transition `CANCELLED` reste
    visible, le pipeline doit relire `job.status` avant chaque finalisation
    DB et bail out si ``CANCELLED`` — sinon il écrase avec ``COMPLETED``.
    TODO (H.2-bis) : ajouter ce guard dans ``jobs/tasks.py``.

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

    job.status = JobStatus.CANCELLED
    await db.commit()
