"""Routeur API pour la gestion des jobs d'upscaling.

Endpoints CRUD (soumission, listing, détail, annulation) et streaming
SSE de la progression en temps réel via Redis Pub/Sub.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_storage
from app.core.redis import get_redis_pool
from app.core.storage.interface import StorageBackend
from app.jobs.schemas import JobCreate, JobResponse
from app.jobs.service import cancel_job, create_job, get_job, list_user_jobs
from app.jobs.sse import stream_job_progress
from app.users.models import User

router = APIRouter(tags=["jobs"])


@router.post("/api/jobs", response_model=JobResponse, status_code=201)
async def submit_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Soumet un nouveau job d'upscaling.

    L'image source doit avoir été uploadée au préalable via ``POST /api/uploads``.
    Le traitement est dispatché à un worker Celery.
    """
    job = await create_job(payload, user, db, storage)
    return JobResponse.model_validate(job)


@router.get("/api/jobs", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[JobResponse]:
    """Liste les jobs de l'utilisateur courant, du plus récent au plus ancien."""
    jobs = await list_user_jobs(user, db)
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_detail(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Retourne le détail d'un job par son ID."""
    job = await get_job(job_id, user, db)
    return JobResponse.model_validate(job)


@router.get("/api/jobs/{job_id}/progress")
async def stream_progress(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream SSE de la progression d'un job en temps réel.

    Le flux émet des événements ``progress``, ``completed`` ou ``error``
    puis se ferme automatiquement quand le job atteint un état terminal.
    Des commentaires keepalive maintiennent la connexion ouverte.
    """
    job = await get_job(job_id, user, db)
    redis: Redis = get_redis_pool()

    return StreamingResponse(
        stream_job_progress(redis, str(job.id), initial_status=job.status),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/jobs/{job_id}/download")
async def download_job_result(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> Response:
    """Télécharge le fichier résultat d'un job terminé avec succès.

    Raises:
        HTTPException: 404 si le job n'existe pas.
        HTTPException: 409 si le job n'est pas encore complété.
    """
    job = await get_job(job_id, user, db)

    if job.status != "completed" or job.output_key is None:
        raise HTTPException(
            status_code=409,
            detail=f"Résultat indisponible — statut actuel : {job.status}",
        )

    try:
        data = await storage.download(job.output_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Fichier résultat introuvable : {job.output_key}",
        ) from exc

    filename = Path(job.output_key).name
    media_type = _guess_media_type(filename)

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


def _guess_media_type(filename: str) -> str:
    """Devine le Content-Type à partir de l'extension du fichier.

    Args:
        filename: Nom du fichier avec extension.

    Returns:
        Type MIME correspondant (``image/png`` par défaut).
    """
    ext = Path(filename).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }.get(ext, "image/png")


@router.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Annule un job en attente (statut pending ou queued uniquement)."""
    await cancel_job(job_id, user, db)
