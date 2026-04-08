"""Schemas Pydantic pour le module d'upload d'images."""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Métadonnées retournées après un upload d'image réussi.

    Attributes:
        key: Clé de stockage générée (ex. ``uploads/{uuid}.png``).
        original_filename: Nom du fichier envoyé par le client.
        content_type: Type MIME du fichier.
        size_bytes: Taille du fichier en octets.
        width: Largeur de l'image en pixels.
        height: Hauteur de l'image en pixels.
    """

    key: str
    original_filename: str
    content_type: str
    size_bytes: int
    width: int
    height: int
