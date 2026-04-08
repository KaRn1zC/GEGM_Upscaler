"""Routeur API pour la gestion des jobs d'upscaling.

Endpoints CRUD : soumission, listing, détail et annulation.
Le streaming SSE de progression (``GET /api/jobs/{id}/progress``)
sera ajouté à l'étape suivante.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_storage
from app.core.storage.interface import StorageBackend
from app.jobs.schemas import JobCreate, JobResponse
from app.jobs.service import cancel_job, create_job, get_job, list_user_jobs
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


@router.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Annule un job en attente (statut pending ou queued uniquement)."""
    await cancel_job(job_id, user, db)
