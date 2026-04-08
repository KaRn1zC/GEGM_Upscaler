"""Logique métier pour l'upload et la validation d'images.

Valide le format, extrait les dimensions via Pillow et stocke le fichier
via le backend de stockage configuré.
"""

import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.core.storage.interface import StorageBackend
from app.uploads.schemas import UploadResponse

ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}
MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 Mo


async def process_upload(file: UploadFile, storage: StorageBackend) -> UploadResponse:
    """Valide une image uploadée, la stocke et retourne ses métadonnées.

    Args:
        file: Fichier reçu via ``UploadFile`` de FastAPI.
        storage: Backend de stockage actif.

    Returns:
        Métadonnées de l'image stockée (clé, dimensions, taille).

    Raises:
        HTTPException: 400 si le format est invalide ou l'image corrompue.
        HTTPException: 413 si le fichier dépasse 100 Mo.
    """
    filename = file.filename or "image.png"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Acceptés : {allowed}",
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 100 Mo)")

    try:
        img = Image.open(BytesIO(content))
        width, height = img.size
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Fichier corrompu ou format d'image invalide",
        ) from exc

    key = f"uploads/{uuid.uuid4()}{ext}"
    await storage.upload(key, content, file.content_type or "application/octet-stream")

    return UploadResponse(
        key=key,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        width=width,
        height=height,
    )
