"""Schemas Pydantic pour le module de gestion des jobs d'upscaling."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    """Paramètres de soumission d'un job d'upscaling.

    Attributes:
        input_key: Clé de stockage de l'image source (obtenue via ``POST /api/uploads``).
        scale_factor: Facteur de multiplication des dimensions (2x ou 4x).
            Le modèle SR est dérivé automatiquement côté serveur :
            x4 → DRCT-L, x2 → HAT-L. Le client n'a pas à le spécifier.
        prefer_local: Préférence utilisateur pour le routage GPU, calculée
            côté frontend via ``canRunLocalStrict()``. ``True`` = tenter le
            Core ML local (si image ≤ 5 MP et backend dispo) ; ``False`` =
            forcer le cloud (RunPod) même pour les petites images. ``None``
            laisse le routeur décider selon les dimensions uniquement
            (comportement legacy).
    """

    input_key: str
    scale_factor: Literal[2, 4] = 4
    prefer_local: bool | None = None


class JobResponse(BaseModel):
    """Représentation complète d'un job en sortie d'API.

    Construit directement depuis l'ORM grâce à ``from_attributes=True``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    input_key: str
    output_key: str | None
    scale_factor: int
    model_name: str
    input_width: int
    input_height: int
    output_width: int | None
    output_height: int | None
    gpu_backend: str | None
    prefer_local: bool | None
    progress: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
