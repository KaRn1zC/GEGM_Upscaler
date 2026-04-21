"""Routeur API pour l'upload d'images."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.dependencies import get_current_user, get_storage
from app.core.media import guess_media_type
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


@router.get("/api/uploads/{key:path}")
async def get_upload(
    key: str,
    storage: StorageBackend = Depends(get_storage),
    _user: User = Depends(get_current_user),
) -> Response:
    """Sert un fichier source déjà uploadé (affichage avant/après).

    Utilisé par la UI pour afficher l'image originale dans le
    ``CompareSlider``. Le segment ``{key:path}`` capte la clé complète
    (ex. ``uploads/<uuid>.png``), quelle que soit sa profondeur.

    Note:
        En prod avec ``S3StorageBackend``, cet endpoint est conservé pour
        compatibilité mais on préférera pointer directement sur des
        presigned URLs générées par ``storage.get_presigned_url(key)`` —
        elles évitent de faire transiter les bytes par l'API FastAPI et
        suppriment la nécessité du query param ``?token=``.

    Raises:
        HTTPException: 404 si la clé n'existe pas dans le storage.
    """
    try:
        data = await storage.download(key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Fichier introuvable : {key}",
        ) from exc

    media_type = guess_media_type(Path(key).name)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Length": str(len(data))},
    )
