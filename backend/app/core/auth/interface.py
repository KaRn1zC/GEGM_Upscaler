"""Interface abstraite pour les backends d'authentification.

Implémentations concrètes :
- ``StaticTokenAuth`` : développement (token statique dans le header).
- ``OIDCAuth`` : production (validation JWT via authlib).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Identité d'un utilisateur authentifié.

    Attributes:
        id: Identifiant unique de l'utilisateur.
        email: Adresse email (peut être absente en auth par token).
        name: Nom d'affichage (peut être absent en auth par token).
    """

    id: str
    email: str | None = None
    name: str | None = None


class AuthBackend(ABC):
    """Classe abstraite pour les backends d'authentification.

    La méthode ``get_current_user`` valide les credentials et retourne
    l'identité authentifiée. Le code métier ne manipule jamais directement
    les tokens ou JWT.
    """

    @abstractmethod
    async def get_current_user(self, credentials: str) -> AuthenticatedUser:
        """Valide les credentials et retourne l'utilisateur authentifié.

        Args:
            credentials: Bearer token extrait du header Authorization.

        Returns:
            Identité de l'utilisateur authentifié.

        Raises:
            ValueError: Si les credentials sont invalides ou expirés.
        """
