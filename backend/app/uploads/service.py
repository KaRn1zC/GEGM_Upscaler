"""Logique métier pour l'upload et la validation d'images.

Valide le format, extrait les dimensions via Pillow et stocke le fichier
via le backend de stockage configuré. Les limites (taille fichier,
mégapixels) viennent des settings — alignées sur la mémoire du pod API
et les capacités du worker GPU.
"""

import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.core.config import settings
from app.core.storage.interface import StorageBackend
from app.uploads.schemas import UploadResponse

ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}

# Lecture du flux par tranches d'1 Mo : borne la RAM applicative à la
# limite configurée même sur un POST bien plus gros (le multipart est déjà
# spoolé sur disque par Starlette ; le rejet réseau précoce est assuré par
# le check Content-Length du routeur).
_CHUNK_SIZE: int = 1024 * 1024


async def process_upload(file: UploadFile, storage: StorageBackend) -> UploadResponse:
    """Valide une image uploadée, la stocke et retourne ses métadonnées.

    Args:
        file: Fichier reçu via ``UploadFile`` de FastAPI.
        storage: Backend de stockage actif.

    Returns:
        Métadonnées de l'image stockée (clé, dimensions, taille).

    Raises:
        HTTPException: 400 si le format est invalide, l'image corrompue ou
            au-delà du plafond mégapixels.
        HTTPException: 413 si le fichier dépasse ``MAX_UPLOAD_SIZE_MB``.
    """
    filename = file.filename or "image.png"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Acceptés : {allowed}",
        )

    # Un SEUL buffer de bout en bout (validation PIL puis upload storage) :
    # aucune copie des bytes — le pic RAM reste ~1x la taille du fichier.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    buffer = BytesIO()
    while chunk := await file.read(_CHUNK_SIZE):
        buffer.write(chunk)
        if buffer.tell() > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {settings.MAX_UPLOAD_SIZE_MB} Mo)",
            )
    size_bytes = buffer.getbuffer().nbytes

    try:
        # Image.open est paresseux : seul l'en-tête est lu, les dimensions
        # sont disponibles sans décoder les pixels.
        buffer.seek(0)
        img = Image.open(buffer)
        width, height = img.size
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Fichier corrompu ou format d'image invalide",
        ) from exc

    megapixels = (width * height) / 1_000_000
    if megapixels > settings.MAX_INPUT_MEGAPIXELS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Image trop grande : {megapixels:.0f} MP (max {settings.MAX_INPUT_MEGAPIXELS} MP)"
            ),
        )

    key = f"uploads/{uuid.uuid4()}{ext}"
    buffer.seek(0)
    await storage.upload(key, buffer, file.content_type or "application/octet-stream")

    return UploadResponse(
        key=key,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        width=width,
        height=height,
    )
