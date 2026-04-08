"""Backend d'authentification par token statique (développement).

Valide les requêtes en comparant le Bearer token du header Authorization
à une valeur fixe définie dans ``DEV_AUTH_TOKEN``. Usage exclusif en local.
"""

from app.core.auth.interface import AuthBackend, AuthenticatedUser


class StaticTokenAuth(AuthBackend):
    """Authentification par comparaison directe d'un token statique.

    Args:
        token: Valeur de référence (issue de ``DEV_AUTH_TOKEN`` dans le ``.env``).
    """

    def __init__(self, token: str) -> None:
        self._token = token

    async def get_current_user(self, credentials: str) -> AuthenticatedUser:
        """Compare le token reçu et retourne un utilisateur dev fixe.

        Args:
            credentials: Token extrait du header ``Authorization: Bearer <token>``.

        Returns:
            Identité fixe de l'utilisateur de développement.

        Raises:
            ValueError: Si le token ne correspond pas.
        """
        if credentials != self._token:
            raise ValueError("Token invalide")
        return AuthenticatedUser(
            id="dev-user",
            email="dev@gegm.local",
            name="Développeur Local",
        )
