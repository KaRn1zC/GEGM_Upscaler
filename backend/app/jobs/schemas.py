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


class BulkDeleteRequest(BaseModel):
    """Liste d'identifiants de jobs à supprimer en lot.

    Attributes:
        job_ids: Jobs à supprimer. Les ids inconnus, d'un autre utilisateur
            ou encore actifs sont ignorés silencieusement côté service.
    """

    job_ids: list[uuid.UUID]


class BulkDeleteResponse(BaseModel):
    """Résultat d'une suppression en lot.

    Attributes:
        deleted: Nombre de jobs effectivement supprimés.
    """

    deleted: int


class WarmupRequest(BaseModel):
    """Pré-chauffage d'un worker GPU pour un facteur donné.

    Attributes:
        scale_factor: Facteur visé (2 ou 4) — sélectionne le modèle à
            pré-charger/compiler côté worker. Défaut x4 (le plus courant).
    """

    scale_factor: Literal[2, 4] = 4


class WarmupResponse(BaseModel):
    """Résultat d'une demande de pré-warm.

    Attributes:
        warmed: ``True`` si un ping de pré-warm a été émis vers le GPU cloud,
            ``False`` si aucun backend cloud n'est configuré (mode local).
    """

    warmed: bool
