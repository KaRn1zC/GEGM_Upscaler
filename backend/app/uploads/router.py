"""Routeur API pour l'upload d'images."""

from fastapi import APIRouter, Depends, UploadFile

from app.core.dependencies import get_current_user, get_storage
from app.core.storage.interface import StorageBackend
from app.uploads.schemas import UploadResponse
from app.uploads.service import process_upload
from app.users.models import User

router = APIRouter(tags=["uploads"])


@router.post("/api/uploads", response_model=UploadResponse, status_code=201)
async def upload_image(
    file: UploadFile,
    storage: StorageBackend = Depends(get_storage),
    _user: User = Depends(get_current_user),
) -> UploadResponse:
    """Upload d'une image pour un futur job d'upscaling.

    Accepte JPEG, PNG, WebP et TIFF. Taille maximale : 100 Mo.
    Retourne la clé de stockage et les dimensions de l'image.
    """
    return await process_upload(file, storage)
