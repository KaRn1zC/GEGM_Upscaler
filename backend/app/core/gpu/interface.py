"""Interface abstraite pour les backends d'inférence GPU.

Implémentations concrètes :
- ``CoreMLBackend`` : inférence locale Apple Silicon (images <= 5 MP).
- ``RunPodBackend`` : GPU cloud via l'API RunPod Serverless (images > 5 MP).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class GPUJobStatus(StrEnum):
    """États possibles d'un job d'inférence GPU."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UpscaleParams:
    """Paramètres d'un job d'upscaling.

    Attributes:
        scale_factor: Facteur de multiplication des dimensions (2x, 4x).
        model_name: Identifiant du modèle de super-résolution à utiliser.
        output_format: Format d'image de sortie souhaité.
    """

    scale_factor: int = 4
    model_name: str = "realesrgan-x4"
    output_format: str = "png"


@dataclass(frozen=True, slots=True)
class GPUJobResult:
    """État courant et résultat d'un job d'inférence GPU.

    Attributes:
        status: Statut actuel du job.
        progress: Pourcentage d'avancement (0.0 à 1.0).
        output_key: Clé de stockage de l'image résultat (renseigné à la fin).
        error: Message d'erreur (renseigné en cas d'échec).
    """

    status: GPUJobStatus
    progress: float = 0.0
    output_key: str | None = None
    error: str | None = None


class GPUBackend(ABC):
    """Classe abstraite pour les backends d'inférence GPU.

    Le routeur GPU dans ``app.upscaling.router_gpu`` sélectionne le backend
    approprié selon les dimensions de l'image en entrée.
    """

    @abstractmethod
    async def submit_job(self, image_data: bytes, params: UpscaleParams) -> str:
        """Soumet une image pour upscaling par inférence.

        Args:
            image_data: Bytes bruts de l'image (PNG, JPEG, etc.).
            params: Paramètres d'upscaling (facteur, modèle, format).

        Returns:
            Identifiant du job pour le suivi de statut.
        """

    @abstractmethod
    async def get_job_status(self, job_id: str) -> GPUJobResult:
        """Vérifie le statut d'un job soumis.

        Args:
            job_id: Identifiant retourné par ``submit_job``.

        Returns:
            État courant, progression et résultat si terminé.
        """
