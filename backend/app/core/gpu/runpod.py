"""Backend GPU cloud via l'API RunPod Serverless.

Soumet des images à un endpoint RunPod Serverless pour upscaling et
poll le statut jusqu'à complétion. L'image est transmise en base64
dans le payload JSON ; le résultat revient dans le champ ``output``.

L'endpoint RunPod doit exposer un handler compatible avec le format
d'entrée/sortie défini dans ``runpod-worker/handler.py``.
"""

import base64

import httpx
from loguru import logger

from app.core.gpu.interface import GPUBackend, GPUJobResult, GPUJobStatus, UpscaleParams

# Mapping des statuts RunPod vers nos statuts internes.
_STATUS_MAP: dict[str, GPUJobStatus] = {
    "IN_QUEUE": GPUJobStatus.QUEUED,
    "IN_PROGRESS": GPUJobStatus.PROCESSING,
    "COMPLETED": GPUJobStatus.COMPLETED,
    "FAILED": GPUJobStatus.FAILED,
    "CANCELLED": GPUJobStatus.FAILED,
    "TIMED_OUT": GPUJobStatus.FAILED,
}

# Timeout HTTP pour les appels à l'API RunPod (secondes).
_REQUEST_TIMEOUT: float = 30.0


class RunPodBackend(GPUBackend):
    """Client async pour l'API RunPod Serverless.

    Chaque instance est liée à un endpoint spécifique identifié par
    ``endpoint_id``. L'authentification se fait via un token Bearer.
    Les bytes du résultat sont mis en cache en mémoire après
    décodage du payload base64 retourné par le handler RunPod.

    Attributes:
        _api_key: Clé API RunPod.
        _endpoint_id: Identifiant de l'endpoint Serverless.
        _base_url: URL de base construite depuis l'endpoint ID.
        _client: Client HTTP async réutilisable (pool de connexions).
        _output_cache: Cache ``job_id → bytes`` des résultats décodés.
    """

    def __init__(self, api_key: str, endpoint_id: str) -> None:
        """Initialise le client RunPod.

        Args:
            api_key: Clé API RunPod (depuis les secrets).
            endpoint_id: Identifiant de l'endpoint Serverless cible.
        """
        self._api_key = api_key
        self._endpoint_id = endpoint_id
        self._base_url = f"https://api.runpod.ai/v2/{endpoint_id}"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_REQUEST_TIMEOUT,
        )
        self._output_cache: dict[str, bytes] = {}

    async def submit_job(self, image_data: bytes, params: UpscaleParams) -> str:
        """Soumet une image à RunPod pour upscaling.

        Encode l'image en base64 et envoie un POST à l'endpoint ``/run``.
        Le handler RunPod côté serveur décode, traite, et renvoie le
        résultat via le mécanisme de polling ``/status``.

        Args:
            image_data: Bytes bruts de l'image source.
            params: Paramètres d'upscaling (facteur, modèle, format).

        Returns:
            Identifiant du job RunPod pour le suivi de statut.

        Raises:
            RuntimeError: Si l'API RunPod retourne une erreur HTTP.
        """
        payload = {
            "input": {
                "image": base64.b64encode(image_data).decode("ascii"),
                "scale_factor": params.scale_factor,
                "model_name": params.model_name,
                "output_format": params.output_format,
            },
        }

        response = await self._client.post(f"{self._base_url}/run", json=payload)

        if response.status_code != 200:
            logger.error(
                "RunPod submit échoué — HTTP {status} : {body}",
                status=response.status_code,
                body=response.text[:500],
            )
            raise RuntimeError(f"RunPod API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        job_id: str = data["id"]

        logger.info(
            "Job RunPod soumis — id={runpod_id} endpoint={ep}",
            runpod_id=job_id,
            ep=self._endpoint_id,
        )

        return job_id

    async def get_job_status(self, job_id: str) -> GPUJobResult:
        """Poll le statut d'un job RunPod.

        Interroge l'endpoint ``/status/{job_id}`` et mappe la réponse
        vers un ``GPUJobResult`` standardisé.

        Args:
            job_id: Identifiant retourné par ``submit_job``.

        Returns:
            État courant du job avec progression et résultat éventuel.

        Raises:
            RuntimeError: Si l'API RunPod retourne une erreur HTTP.
        """
        response = await self._client.get(f"{self._base_url}/status/{job_id}")

        if response.status_code != 200:
            logger.error(
                "RunPod status échoué — HTTP {status} pour job {job_id}",
                status=response.status_code,
                job_id=job_id,
            )
            raise RuntimeError(f"RunPod API error {response.status_code}: {response.text[:200]}")

        data = response.json()
        runpod_status = data.get("status", "FAILED")
        status = _STATUS_MAP.get(runpod_status, GPUJobStatus.FAILED)

        # Progression estimée selon le statut (RunPod ne donne pas de %).
        progress = _estimate_progress(status)

        # Extraction du résultat ou de l'erreur.
        output_key: str | None = None
        error: str | None = None

        if status == GPUJobStatus.COMPLETED:
            output = data.get("output", {})
            # Le handler RunPod renvoie l'image encodée en base64 dans
            # output.image. On la décode et on la met en cache pour
            # récupération via get_output_data().
            image_b64 = output.get("image")
            if image_b64:
                try:
                    self._output_cache[job_id] = base64.b64decode(image_b64)
                    output_key = job_id
                except (ValueError, TypeError) as exc:
                    logger.error(
                        "RunPod — base64 invalide pour job {job_id} : {err}",
                        job_id=job_id,
                        err=str(exc),
                    )
                    status = GPUJobStatus.FAILED
                    error = f"Base64 output invalide : {exc}"
            else:
                logger.warning(
                    "RunPod — output sans champ 'image' pour job {job_id}",
                    job_id=job_id,
                )
                status = GPUJobStatus.FAILED
                error = "Output RunPod sans champ 'image'"

        if status == GPUJobStatus.FAILED and error is None:
            error = data.get("error", runpod_status)

        return GPUJobResult(
            status=status,
            progress=progress,
            output_key=output_key,
            error=error,
        )

    def get_output_data(self, job_id: str) -> bytes | None:
        """Récupère les bytes du résultat d'un job terminé.

        Les bytes sont mis en cache lors du dernier ``get_job_status``
        retournant COMPLETED. Le cache est volatil : à la fin du worker
        Celery, il est perdu (mais à ce moment le fichier a déjà été
        uploadé dans le storage).

        Args:
            job_id: Identifiant du job RunPod.

        Returns:
            Bytes de l'image upscalée, ou ``None`` si non disponible.
        """
        return self._output_cache.get(job_id)

    async def cancel_job(self, job_id: str) -> None:
        """Annule un job RunPod en cours ou en file d'attente.

        Args:
            job_id: Identifiant du job à annuler.
        """
        response = await self._client.post(f"{self._base_url}/cancel/{job_id}")

        if response.status_code != 200:
            logger.warning(
                "RunPod cancel échoué — HTTP {status} pour job {job_id}",
                status=response.status_code,
                job_id=job_id,
            )

    async def close(self) -> None:
        """Ferme le client HTTP et libère les connexions."""
        await self._client.aclose()


def _estimate_progress(status: GPUJobStatus) -> float:
    """Estime la progression d'un job à partir de son statut.

    RunPod ne fournit pas de pourcentage fin — on utilise des paliers
    fixes basés sur l'état du job.

    Args:
        status: Statut interne du job.

    Returns:
        Estimation de 0.0 à 1.0.
    """
    match status:
        case GPUJobStatus.QUEUED:
            return 0.0
        case GPUJobStatus.PROCESSING:
            return 0.5
        case GPUJobStatus.COMPLETED:
            return 1.0
        case GPUJobStatus.FAILED:
            return 0.0
