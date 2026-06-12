"""Backend GPU cloud via l'API RunPod Serverless.

Soumet des images à un endpoint RunPod Serverless pour upscaling et
poll le statut jusqu'à complétion. L'image est transmise soit en base64
dans le payload JSON (limité à ~10 Mo par l'API ``/run``), soit par URL
présignée que le handler télécharge lui-même (aucune limite de taille) ;
le résultat revient dans le champ ``output``.

Le handler RunPod supporte deux modes de retour :
- ``inline`` : image en base64 dans ``output.image`` (limité à ~20 MB
  par la limite de payload RunPod ``/status``).
- ``s3`` : image uploadée par le handler sur un bucket S3-compatible,
  URL retournée dans ``output.output_url``. Pas de limite de taille.

L'endpoint RunPod doit exposer un handler compatible avec le format
d'entrée/sortie défini dans ``runpod-worker/handler.py``.
"""

from __future__ import annotations

import base64
import contextlib
import os
import tempfile
from typing import TYPE_CHECKING, BinaryIO
from urllib.parse import urlparse

import httpx
from loguru import logger

from app.core.gpu.interface import GPUBackend, GPUJobResult, GPUJobStatus, UpscaleParams

if TYPE_CHECKING:
    # Importé uniquement pour le typing — aioboto3 est une dépendance lourde
    # qu'on ne veut pas charger au démarrage si la config S3 du worker RunPod
    # n'est pas active. L'import réel est fait paresseusement dans ``__init__``.
    import aioboto3

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

    def __init__(
        self,
        api_key: str,
        endpoint_id: str,
        *,
        s3_endpoint_url: str = "",
        s3_bucket: str = "",
        s3_access_key: str = "",
        s3_secret_key: str = "",
        s3_region: str = "auto",
    ) -> None:
        """Initialise le client RunPod.

        Args:
            api_key: Clé API RunPod (depuis les secrets).
            endpoint_id: Identifiant de l'endpoint Serverless cible.
            s3_endpoint_url: URL du bucket S3-compatible où le handler
                upload les outputs volumineux. Vide = mode inline uniquement.
            s3_bucket: Nom du bucket de sortie.
            s3_access_key: Access Key ID pour le bucket.
            s3_secret_key: Secret Access Key pour le bucket.
            s3_region: Région du bucket (``auto`` pour R2/MinIO).
        """
        self._api_key = api_key
        self._endpoint_id = endpoint_id
        self._base_url = f"https://api.runpod.ai/v2/{endpoint_id}"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_REQUEST_TIMEOUT,
        )
        # Petits outputs (mode inline) : bytes en mémoire. Gros outputs
        # (mode S3) : fichier temporaire sur disque, streamé vers le
        # storage sans jamais matérialiser l'image en RAM.
        self._output_cache: dict[str, bytes] = {}
        self._output_files: dict[str, str] = {}

        # Config S3 pour le download des outputs volumineux. Si au moins
        # une variable clef manque, on fallback sur l'inline uniquement.
        self._s3_endpoint_url = s3_endpoint_url
        self._s3_bucket = s3_bucket
        self._s3_region = s3_region
        self._s3_session: aioboto3.Session | None = None
        if s3_endpoint_url and s3_access_key and s3_secret_key:
            import aioboto3

            self._s3_session = aioboto3.Session(
                aws_access_key_id=s3_access_key,
                aws_secret_access_key=s3_secret_key,
                region_name=s3_region,
            )

    supports_url_input = True

    async def submit_job(
        self,
        image_data: bytes | None,
        params: UpscaleParams,
        *,
        image_url: str | None = None,
        execution_timeout_s: int | None = None,
    ) -> str:
        """Soumet une image à RunPod pour upscaling.

        Envoie un POST à l'endpoint ``/run``. L'image part de préférence
        en ``image_url`` (URL présignée que le handler télécharge — aucune
        limite de taille), sinon en base64 inline (limite ~10 Mo de payload
        JSON, soit ~7,3 Mo de fichier réel). Le handler décode, traite, et
        renvoie le résultat via le mécanisme de polling ``/status``.

        Args:
            image_data: Bytes bruts de l'image source (mode inline), ou
                ``None`` si ``image_url`` est fournie.
            params: Paramètres d'upscaling (facteur, modèle, format).
            image_url: URL présignée de l'image source (mode URL, préféré).
            execution_timeout_s: Timeout d'exécution par job, transmis à
                RunPod via ``policy.executionTimeout`` (prioritaire sur le
                défaut de l'endpoint). ``None`` = défaut endpoint.

        Returns:
            Identifiant du job RunPod pour le suivi de statut.

        Raises:
            ValueError: Si ni ``image_data`` ni ``image_url`` n'est fourni.
            RuntimeError: Si l'API RunPod retourne une erreur HTTP.
        """
        inputs: dict[str, object] = {
            "scale_factor": params.scale_factor,
            "model_name": params.model_name,
            "output_format": params.output_format,
        }
        if image_url:
            inputs["image_url"] = image_url
        elif image_data is not None:
            inputs["image"] = base64.b64encode(image_data).decode("ascii")
        else:
            raise ValueError("submit_job : ni image_data ni image_url fourni")

        payload: dict[str, object] = {"input": inputs}
        if execution_timeout_s is not None:
            # La policy RunPod s'exprime en millisecondes.
            payload["policy"] = {"executionTimeout": execution_timeout_s * 1000}

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
            # Le handler renvoie soit l'image en base64 (output.image), soit
            # une URL S3 (output.output_url) pour les résultats volumineux.
            output_url = output.get("output_url")
            image_b64 = output.get("image")
            if output_url:
                try:
                    self._output_files[job_id] = await self._download_s3_to_file(output_url)
                    output_key = job_id
                except Exception as exc:
                    logger.error(
                        "RunPod — download S3 échoué pour job {job_id} : {err}",
                        job_id=job_id,
                        err=str(exc),
                    )
                    status = GPUJobStatus.FAILED
                    error = f"Download output S3 échoué : {exc}"
            elif image_b64:
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
                    "RunPod — output sans 'image' ni 'output_url' pour job {job_id}",
                    job_id=job_id,
                )
                status = GPUJobStatus.FAILED
                error = "Output RunPod sans 'image' ni 'output_url'"

        if status == GPUJobStatus.FAILED and error is None:
            error = data.get("error", runpod_status)

        return GPUJobResult(
            status=status,
            progress=progress,
            output_key=output_key,
            error=error,
        )

    def get_output_data(self, job_id: str) -> bytes | BinaryIO | None:
        """Récupère le résultat d'un job terminé.

        Mode inline : bytes décodés du base64, sortis du cache (pop — un
        seul consommateur, libère la RAM au plus tôt). Mode S3 : flux
        ouvert sur le fichier temporaire téléchargé, à streamer vers le
        storage — l'image ne transite jamais entière en RAM. Le fichier
        sous-jacent est supprimé par ``close()``.

        Args:
            job_id: Identifiant du job RunPod.

        Returns:
            Bytes ou flux binaire de l'image upscalée, ou ``None``.
        """
        path = self._output_files.get(job_id)
        if path is not None:
            return open(path, "rb")
        return self._output_cache.pop(job_id, None)

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
        """Ferme le client HTTP et nettoie les fichiers temporaires d'output."""
        await self._client.aclose()
        for path in self._output_files.values():
            with contextlib.suppress(OSError):
                os.unlink(path)
        self._output_files.clear()

    async def _download_s3_to_file(self, url: str) -> str:
        """Télécharge un objet S3 (``s3://bucket/key``) vers un fichier temporaire.

        Utilisé pour récupérer les outputs volumineux que le handler RunPod
        a uploadés directement sur le bucket (bypass la limite de 20 MB du
        payload ``/status``). Le téléchargement est streamé par chunks vers
        le disque (``/tmp`` du pod) : une image upscalée de plusieurs Go ne
        passe jamais entière en RAM. Le fichier est supprimé par ``close()``.

        Args:
            url: URL au format ``s3://<bucket>/<key>``.

        Returns:
            Chemin du fichier temporaire contenant l'objet.

        Raises:
            RuntimeError: Si la config S3 output est incomplète ou si
                l'URL ne correspond pas au bucket configuré.
        """
        if self._s3_session is None:
            raise RuntimeError(
                "Output S3 reçu mais aucune config S3_OUTPUT_* dans les settings — "
                "impossible de télécharger"
            )

        parsed = urlparse(url)
        if parsed.scheme != "s3":
            raise RuntimeError(f"URL output inattendue (scheme != s3) : {url}")

        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise RuntimeError(f"URL output mal formée : {url}")

        fd, path = tempfile.mkstemp(prefix="runpod-output-", suffix=".bin")
        try:
            async with self._s3_session.client("s3", endpoint_url=self._s3_endpoint_url) as s3:
                with os.fdopen(fd, "wb") as f:
                    await s3.download_fileobj(bucket, key, f)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(path)
            raise
        return path


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
