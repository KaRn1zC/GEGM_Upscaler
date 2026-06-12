"""Interface abstraite pour les backends d'inférence GPU.

Implémentations concrètes :
- ``CoreMLBackend`` : inférence locale Apple Silicon (images <= 5 MP).
- ``RunPodBackend`` : GPU cloud via l'API RunPod Serverless (images > 5 MP).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


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
    model_name: str = "drct-l"
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

    Attributes:
        supports_url_input: ``True`` si le backend sait récupérer l'image
            source lui-même depuis une URL HTTP(S) (``image_url`` de
            ``submit_job``). Permet au pipeline de passer une URL présignée
            au lieu de transférer les bytes — indispensable au-delà de la
            limite de payload des APIs cloud (RunPod : ~10 Mo).
    """

    supports_url_input: ClassVar[bool] = False

    @abstractmethod
    async def submit_job(
        self,
        image_data: bytes | None,
        params: UpscaleParams,
        *,
        image_url: str | None = None,
        execution_timeout_s: int | None = None,
    ) -> str:
        """Soumet une image pour upscaling par inférence.

        Au moins un de ``image_data`` / ``image_url`` doit être fourni.
        ``image_url`` n'est honorée que si ``supports_url_input`` est vrai —
        les backends locaux exigent les bytes.

        Args:
            image_data: Bytes bruts de l'image (PNG, JPEG, etc.), ou ``None``
                si l'image est fournie via ``image_url``.
            params: Paramètres d'upscaling (facteur, modèle, format).
            image_url: URL HTTP(S) présignée de l'image source, téléchargeable
                par le backend lui-même (évite le transfert des bytes).
            execution_timeout_s: Durée max d'exécution accordée au job côté
                provider, en secondes. ``None`` = défaut de l'endpoint.

        Returns:
            Identifiant du job pour le suivi de statut.

        Raises:
            ValueError: Si ni ``image_data`` ni ``image_url`` n'est fourni,
                ou si seul ``image_url`` est fourni à un backend qui ne le
                supporte pas.
        """

    @abstractmethod
    async def get_job_status(self, job_id: str) -> GPUJobResult:
        """Vérifie le statut d'un job soumis.

        Args:
            job_id: Identifiant retourné par ``submit_job``.

        Returns:
            État courant, progression et résultat si terminé.
        """

    # No-op volontaire (pas @abstractmethod) : seuls les backends cloud en
    # ont besoin, les backends locaux ne doivent rien avoir à implémenter.
    async def cancel_job(self, job_id: str) -> None:  # noqa: B027
        """Annule un job en cours côté provider.

        No-op par défaut — seuls les backends cloud facturés à la durée
        (RunPod) ont intérêt à l'implémenter. Appelé notamment quand le
        polling client abandonne (timeout) pour ne pas laisser tourner
        un job orphelin facturé.

        Args:
            job_id: Identifiant retourné par ``submit_job``.
        """

    async def close(self) -> None:  # noqa: B027 — no-op volontaire, cf. cancel_job
        """Libère les ressources du backend (clients HTTP, sessions).

        No-op par défaut. ``RunPodBackend`` ferme son pool de connexions
        httpx ici — à appeler en fin de tâche pour éviter la fuite de
        descripteurs à chaque job.
        """

    @abstractmethod
    def get_output_data(self, job_id: str) -> bytes | None:
        """Récupère les bytes de l'image résultat d'un job terminé.

        Chaque backend stocke le résultat en mémoire après complétion
        (Core ML dans un dict interne, RunPod dans un cache après
        décodage du payload base64). Les bytes doivent rester disponibles
        au moins jusqu'à ce que le worker Celery les ait uploadés dans
        le storage.

        Args:
            job_id: Identifiant retourné par ``submit_job``.

        Returns:
            Bytes de l'image upscalée, ou ``None`` si indisponible.
        """
