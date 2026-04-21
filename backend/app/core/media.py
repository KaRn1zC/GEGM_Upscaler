"""Utilitaires partagés pour la détection de type MIME d'images.

Centralise la logique pour éviter la duplication entre les routers
``uploads`` (sert les inputs) et ``jobs`` (sert les outputs).
"""

from pathlib import Path

_EXTENSION_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def guess_media_type(filename: str) -> str:
    """Devine le Content-Type à partir de l'extension du fichier.

    Args:
        filename: Nom du fichier avec extension (casse indifférente).

    Returns:
        Type MIME correspondant (``image/png`` par défaut pour les
        extensions inconnues ou absentes).
    """
    ext = Path(filename).suffix.lower()
    return _EXTENSION_MIME.get(ext, "image/png")
