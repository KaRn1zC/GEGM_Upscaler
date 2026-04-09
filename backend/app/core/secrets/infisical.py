"""Backend de gestion des secrets via Infisical (API REST).

Implémentation de ``SecretsBackend`` pour récupérer des secrets depuis
Infisical, un gestionnaire open-source alternatif à HashiCorp Vault.

Utilise l'API REST directe (pas le SDK officiel) pour éviter d'ajouter
une dépendance lourde, et pour rester aligné sur le pattern des autres
backends de l'application (httpx comme client HTTP unique).

Authentification via ``Authorization: Bearer <token>``. Le token peut être :
- Un **service token** (recommandé pour les apps prod)
- Un **machine identity token** (OAuth-like, renouvelable)

Documentation : https://infisical.com/docs/api-reference/endpoints/secrets/get-raw
"""

import httpx
from loguru import logger

from app.core.secrets.interface import SecretsBackend

# Timeout HTTP pour les appels Infisical.
_HTTP_TIMEOUT: float = 10.0

# URL par défaut de l'instance SaaS Infisical. Peut être overridée pour
# pointer sur une instance self-hosted.
_DEFAULT_API_URL: str = "https://app.infisical.com/api"


class InfisicalSecretsBackend(SecretsBackend):
    """Récupération de secrets depuis Infisical.

    Args:
        token: Service token ou machine identity token Infisical.
        project_id: Identifiant du workspace Infisical contenant les secrets.
        environment: Environnement cible (``dev``, ``staging``, ``prod``).
        api_url: URL de l'API. Par défaut l'instance SaaS publique.
    """

    def __init__(
        self,
        token: str,
        project_id: str = "",
        environment: str = "prod",
        api_url: str = _DEFAULT_API_URL,
    ) -> None:
        if not token:
            raise ValueError("InfisicalSecretsBackend : token ne peut pas être vide")

        self._token = token
        self._project_id = project_id
        self._environment = environment
        self._api_url = api_url.rstrip("/")

    async def get(self, key: str) -> str:
        """Récupère la valeur d'un secret depuis Infisical.

        Args:
            key: Nom du secret à récupérer (ex. ``DATABASE_URL``, ``RUNPOD_API_KEY``).

        Returns:
            Valeur du secret en clair.

        Raises:
            KeyError: Si le secret n'existe pas dans le projet/environnement.
            RuntimeError: Pour toute autre erreur (réseau, 401, 500, etc.).
        """
        url = f"{self._api_url}/v3/secrets/raw/{key}"
        params: dict[str, str] = {"environment": self._environment}
        if self._project_id:
            params["workspaceId"] = self._project_id

        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Infisical — erreur réseau pour {key} : {err}", key=key, err=str(exc))
            raise RuntimeError(f"Erreur réseau Infisical : {exc}") from exc

        if response.status_code == 404:
            raise KeyError(f"Secret introuvable dans Infisical : {key}")

        if response.status_code == 401:
            raise RuntimeError("Token Infisical invalide ou expiré")

        if response.status_code != 200:
            logger.error(
                "Infisical — HTTP {status} pour {key} : {body}",
                status=response.status_code,
                key=key,
                body=response.text[:200],
            )
            raise RuntimeError(
                f"Infisical API error {response.status_code} : {response.text[:200]}",
            )

        try:
            secret_data = response.json()["secret"]
            value: str = secret_data["secretValue"]
        except (KeyError, ValueError) as exc:
            logger.error("Infisical — réponse malformée pour {key}", key=key)
            raise RuntimeError(f"Réponse Infisical malformée : {exc}") from exc

        return value
