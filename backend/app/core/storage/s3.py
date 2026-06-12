"""Backend de stockage S3-compatible (AWS S3, Cloudflare R2, GCS, MinIO).

Implémentation de ``StorageBackend`` reposant sur ``aioboto3``. Supporte
n'importe quel service compatible avec l'API S3 via le paramètre
``endpoint_url`` :

- AWS S3 : ne pas fournir ``endpoint_url`` (valeur par défaut).
- Cloudflare R2 : ``https://<account>.r2.cloudflarestorage.com``.
- GCS (compat S3) : ``https://storage.googleapis.com``.
- MinIO : ``http://minio:9000`` ou l'URL du serveur local.

Les crédentials sont fournis via les paramètres constructeur et proviennent
typiquement d'un ``SecretsBackend`` (Infisical, Vault, env).
"""

from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO

from loguru import logger

from app.core.storage.interface import StorageBackend

if TYPE_CHECKING:
    # Importé uniquement pour le typing — aioboto3 est une dépendance lourde
    # que l'on ne veut pas charger au démarrage si le backend S3 n'est pas
    # actif. L'import réel est fait paresseusement dans ``_session``.
    import aioboto3


class S3StorageBackend(StorageBackend):
    """Stockage de fichiers sur un bucket S3-compatible.

    Chaque opération ouvre une session ``aioboto3`` dédiée pour éviter les
    problèmes de partage entre event loops (Celery workers, requêtes HTTP
    concurrentes). Le coût est négligeable puisque les connexions HTTP
    sous-jacentes sont poolées par aiohttp.

    Args:
        bucket: Nom du bucket cible.
        endpoint_url: URL de l'API S3. Chaîne vide pour AWS S3 standard.
        access_key: Clé d'accès (``AWS_ACCESS_KEY_ID`` ou équivalent).
        secret_key: Clé secrète (``AWS_SECRET_ACCESS_KEY`` ou équivalent).
        region: Région (``auto`` pour R2, ``us-east-1`` pour AWS par défaut).
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
    ) -> None:
        if not bucket:
            raise ValueError("S3StorageBackend : bucket ne peut pas être vide")
        if not access_key or not secret_key:
            raise ValueError("S3StorageBackend : access_key et secret_key requis")

        self._bucket = bucket
        self._endpoint_url = endpoint_url or None
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region or "auto"

    def _session(self) -> "aioboto3.Session":
        """Crée une session aioboto3 — import paresseux pour ne pas charger la lib au démarrage."""
        import aioboto3

        return aioboto3.Session()

    def _client_kwargs(self) -> dict[str, str]:
        """Arguments communs à tous les appels ``session.client("s3", ...)``."""
        kwargs: dict[str, str] = {
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._region,
        }
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return kwargs

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Envoie un fichier dans le bucket S3.

        Args:
            key: Clé de stockage (chemin relatif type ``uploads/abc.png``).
            data: Contenu en bytes ou flux binaire.
            content_type: Type MIME (utilisé par S3 pour les téléchargements directs).

        Returns:
            La clé de stockage du fichier uploadé.

        Raises:
            RuntimeError: Si l'upload S3 échoue.
        """
        # upload_fileobj bascule automatiquement en multipart au-delà de
        # 8 Mo (chunks streamés) — indispensable pour les gros fichiers :
        # pas de PUT monolithique qui duplique tout le buffer, et plus de
        # plafond des 5 Go du put_object simple.
        stream: BinaryIO = BytesIO(data) if isinstance(data, bytes) else data

        session = self._session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.upload_fileobj(
                    stream,
                    self._bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
            except Exception as exc:
                logger.error(
                    "Upload S3 échoué — bucket={b} key={k} err={e}",
                    b=self._bucket,
                    k=key,
                    e=str(exc),
                )
                raise RuntimeError(f"Upload S3 échoué : {exc}") from exc

        return key

    async def download(self, key: str) -> bytes:
        """Télécharge un fichier depuis le bucket.

        Args:
            key: Clé de stockage du fichier.

        Returns:
            Contenu du fichier en bytes.

        Raises:
            FileNotFoundError: Si la clé n'existe pas dans le bucket.
            RuntimeError: Pour toute autre erreur S3.
        """
        session = self._session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                error_code = _extract_s3_error_code(exc)
                if error_code in ("NoSuchKey", "404"):
                    raise FileNotFoundError(f"Fichier introuvable : {key}") from exc
                logger.error(
                    "Download S3 échoué — bucket={b} key={k} err={e}",
                    b=self._bucket,
                    k=key,
                    e=str(exc),
                )
                raise RuntimeError(f"Download S3 échoué : {exc}") from exc

            async with response["Body"] as stream:
                data: bytes = await stream.read()
                return data

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Génère une URL présignée pour télécharger directement le fichier.

        Args:
            key: Clé de stockage du fichier.
            expires_in: Durée de validité de l'URL en secondes.

        Returns:
            URL HTTPS signée, utilisable directement par le navigateur.

        Raises:
            RuntimeError: Si la génération d'URL échoue.
        """
        session = self._session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                url: str = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
            except Exception as exc:
                logger.error(
                    "Génération presigned URL échouée — key={k} err={e}",
                    k=key,
                    e=str(exc),
                )
                raise RuntimeError(f"Génération presigned URL échouée : {exc}") from exc

        return url

    async def delete(self, key: str) -> None:
        """Supprime un fichier du bucket.

        Vérifie d'abord l'existence via ``head_object`` pour respecter le
        contrat de l'interface (``FileNotFoundError`` sur clé inconnue) —
        S3 ``delete_object`` est idempotent et ne lève pas sur clé absente.

        Args:
            key: Clé de stockage du fichier à supprimer.

        Raises:
            FileNotFoundError: Si la clé n'existe pas.
            RuntimeError: Pour toute autre erreur S3.
        """
        session = self._session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                error_code = _extract_s3_error_code(exc)
                if error_code in ("NoSuchKey", "404", "NotFound"):
                    raise FileNotFoundError(f"Fichier introuvable : {key}") from exc
                logger.error(
                    "Vérification head_object échouée — key={k} err={e}",
                    k=key,
                    e=str(exc),
                )
                raise RuntimeError(f"Vérification S3 échouée : {exc}") from exc

            try:
                await s3.delete_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                logger.error(
                    "Suppression S3 échouée — key={k} err={e}",
                    k=key,
                    e=str(exc),
                )
                raise RuntimeError(f"Suppression S3 échouée : {exc}") from exc


def _extract_s3_error_code(exc: Exception) -> str | None:
    """Extrait le code d'erreur S3 depuis une ``ClientError`` botocore.

    botocore encode le détail de l'erreur dans ``exc.response["Error"]["Code"]``.
    Si l'exception n'est pas une ``ClientError`` ou que la structure diffère,
    retourne ``None`` pour que l'appelant retombe sur un traitement générique.

    Args:
        exc: Exception levée par un appel aioboto3.

    Returns:
        Code d'erreur S3 (ex. ``NoSuchKey``) ou ``None``.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return str(code) if code is not None else None
