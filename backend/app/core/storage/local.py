"""Backend de stockage local sur le filesystem.

Implémentation de ``StorageBackend`` pour le développement local.
Les fichiers sont stockés sous ``LOCAL_STORAGE_PATH`` (configurable via ``.env``).
"""

import asyncio
from pathlib import Path
from typing import BinaryIO

from app.core.storage.interface import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Stockage de fichiers sur le filesystem local.

    Les clés (``key``) correspondent à des chemins relatifs sous le
    répertoire de base. Les sous-répertoires sont créés automatiquement.
    Une validation empêche toute traversée de chemin (``../``).

    Args:
        base_path: Répertoire racine du stockage (ex. ``/data``).
    """

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path).resolve()

    def _resolve_path(self, key: str) -> Path:
        """Résout la clé en chemin absolu, avec protection contre la traversée.

        Args:
            key: Clé relative (ex. ``uploads/abc123.png``).

        Returns:
            Chemin absolu vers le fichier.

        Raises:
            ValueError: Si la clé tente de sortir du répertoire de base.
        """
        path = (self._base_path / key).resolve()
        if not path.is_relative_to(self._base_path):
            raise ValueError(f"Clé invalide — traversée de chemin détectée : {key}")
        return path

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Écrit un fichier sur le disque local.

        Crée automatiquement les répertoires intermédiaires si nécessaire.

        Args:
            key: Clé de stockage (chemin relatif).
            data: Contenu en bytes bruts ou flux binaire (ex. ``UploadFile.file``).
            content_type: Type MIME (ignoré en local, conservé pour l'interface).

        Returns:
            La clé de stockage du fichier écrit.

        Raises:
            ValueError: Si la clé contient une traversée de chemin.
        """
        path = self._resolve_path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)

        raw = data if isinstance(data, bytes) else await asyncio.to_thread(data.read)
        await asyncio.to_thread(path.write_bytes, raw)
        return key

    async def download(self, key: str) -> bytes:
        """Lit un fichier depuis le disque local.

        Args:
            key: Clé de stockage du fichier.

        Returns:
            Contenu du fichier en bytes.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si la clé contient une traversée de chemin.
        """
        path = self._resolve_path(key)
        if not await asyncio.to_thread(path.exists):
            raise FileNotFoundError(f"Fichier introuvable : {key}")
        return await asyncio.to_thread(path.read_bytes)

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Retourne un chemin d'API pour le téléchargement local.

        En mode local, pas de signature — retourne un chemin relatif
        que le frontend peut appeler directement sur l'API.

        Args:
            key: Clé de stockage du fichier.
            expires_in: Ignoré en local (pas d'expiration).

        Returns:
            Chemin d'API sous la forme ``/api/files/{key}``.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si la clé contient une traversée de chemin.
        """
        path = self._resolve_path(key)
        if not await asyncio.to_thread(path.exists):
            raise FileNotFoundError(f"Fichier introuvable : {key}")
        return f"/api/files/{key}"

    async def delete(self, key: str) -> None:
        """Supprime un fichier du disque local.

        Args:
            key: Clé de stockage du fichier à supprimer.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si la clé contient une traversée de chemin.
        """
        path = self._resolve_path(key)
        if not await asyncio.to_thread(path.exists):
            raise FileNotFoundError(f"Fichier introuvable : {key}")
        await asyncio.to_thread(path.unlink)
