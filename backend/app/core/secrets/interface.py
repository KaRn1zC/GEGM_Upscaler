"""Interface abstraite pour la gestion des secrets.

Implémentations concrètes :
- ``EnvSecretsBackend`` : développement (``os.environ`` via python-dotenv).
- ``InfisicalSecretsBackend`` / ``VaultSecretsBackend`` : production.
"""

from abc import ABC, abstractmethod


class SecretsBackend(ABC):
    """Classe abstraite pour les backends de gestion des secrets.

    Expose une unique méthode ``get()`` pour récupérer un secret par son nom.
    Découple le code applicatif du fournisseur de secrets réel.
    """

    @abstractmethod
    async def get(self, key: str) -> str:
        """Récupère la valeur d'un secret par sa clé.

        Args:
            key: Nom du secret à récupérer.

        Returns:
            Valeur du secret sous forme de chaîne.

        Raises:
            KeyError: Si le secret n'existe pas.
        """
