"""Interface abstraite pour les opérations de stockage de fichiers.

Le code métier interagit exclusivement avec cette interface.
Les implémentations concrètes (filesystem local, S3/R2/GCS) sont
injectées à l'exécution via ``app.core.dependencies`` selon la configuration.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    """Classe abstraite pour les backends de stockage.

    Toute implémentation doit fournir les quatre opérations de base :
    upload, download, génération d'URL présignée et suppression.
    """

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Envoie un fichier vers le stockage.

        Args:
            key: Clé unique (chemin) du fichier dans le stockage.
            data: Contenu du fichier en bytes ou flux binaire.
            content_type: Type MIME du fichier.

        Returns:
            La clé de stockage du fichier uploadé.
        """

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Télécharge un fichier depuis le stockage.

        Args:
            key: Clé de stockage du fichier à récupérer.

        Returns:
            Contenu du fichier en bytes.

        Raises:
            FileNotFoundError: Si la clé n'existe pas.
        """

    @abstractmethod
    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Génère une URL présignée pour accès direct au fichier.

        En local, retourne un chemin de téléchargement direct.
        Pour les backends S3-compatibles, une URL signée à durée limitée.

        Args:
            key: Clé de stockage du fichier.
            expires_in: Durée de validité de l'URL en secondes.

        Returns:
            URL d'accès direct sous forme de chaîne.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Supprime un fichier du stockage.

        Args:
            key: Clé de stockage du fichier à supprimer.

        Raises:
            FileNotFoundError: Si la clé n'existe pas.
        """
