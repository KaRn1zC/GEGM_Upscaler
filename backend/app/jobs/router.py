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
from app.core.media import guess_media_type
from app.core.redis import get_redis_pool
from app.core.storage.interface import StorageBackend
from app.jobs.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    JobCreate,
    JobResponse,
    WarmupRequest,
    WarmupResponse,
)
from app.jobs.service import (
    bulk_delete_jobs,
    cancel_job,
    create_job,
    delete_job,
    get_job,
    list_user_jobs,
    warmup_gpu,
)
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


@router.post("/api/warmup", response_model=WarmupResponse)
async def warmup(
    payload: WarmupRequest,
    user: User = Depends(get_current_user),
) -> WarmupResponse:
    """Pré-chauffe un worker GPU (best-effort, fire-and-forget).

    Appelé par le frontend à l'ouverture de l'app / au changement de facteur :
    déclenche le chargement du modèle + la compilation ``torch.compile`` côté
    worker pendant que l'utilisateur prépare son upload, pour masquer le
    cold-start (~280 s) du premier vrai upscale. Ne bloque pas sur l'inférence
    et n'échoue jamais sur un souci de pré-warm.
    """
    warmed = await warmup_gpu(payload.scale_factor)
    return WarmupResponse(warmed=warmed)


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
    media_type = guess_media_type(filename)

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


@router.post("/api/jobs/{job_id}/cancel", status_code=204)
async def cancel_job_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Annule un job actif (pending, queued ou processing).

    Stoppe aussi l'inférence RunPod en cours le cas échéant (pas de
    facturation orpheline). Pour retirer définitivement un job terminé et
    ses fichiers, voir ``DELETE /api/jobs/{job_id}``.
    """
    await cancel_job(job_id, user, db)


@router.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> None:
    """Supprime un job terminé : fichiers (input + output) puis ligne DB.

    Réservé aux jobs terminés (completed, failed, cancelled) — un job actif
    doit d'abord être annulé via ``POST /api/jobs/{job_id}/cancel``.
    """
    await delete_job(job_id, user, db, storage)


@router.post("/api/jobs/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_jobs_endpoint(
    payload: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> BulkDeleteResponse:
    """Supprime en lot les jobs terminés de l'utilisateur (nettoyage de masse).

    Tolérant : ignore silencieusement les ids inconnus, d'un autre user ou
    encore actifs. Retourne le nombre réellement supprimé.
    """
    deleted = await bulk_delete_jobs(payload.job_ids, user, db, storage)
    return BulkDeleteResponse(deleted=deleted)
