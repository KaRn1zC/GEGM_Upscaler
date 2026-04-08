"""Backend de secrets via variables d'environnement (développement).

Lecture directe depuis ``os.environ``. Les valeurs proviennent du
fichier ``.env`` chargé par pydantic-settings au démarrage.
"""

import os

from app.core.secrets.interface import SecretsBackend


class EnvSecretsBackend(SecretsBackend):
    """Récupération de secrets depuis les variables d'environnement système.

    Implémentation minimale pour le développement local. En production,
    remplacée par Infisical ou Vault via le ``.env``.
    """

    async def get(self, key: str) -> str:
        """Lit un secret depuis ``os.environ``.

        Args:
            key: Nom de la variable d'environnement.

        Returns:
            Valeur de la variable.

        Raises:
            KeyError: Si la variable n'existe pas.
        """
        value = os.environ.get(key)
        if value is None:
            raise KeyError(f"Variable d'environnement introuvable : {key}")
        return value
