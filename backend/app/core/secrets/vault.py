"""Backend de gestion des secrets via HashiCorp Vault (API REST, KV v2).

Implémentation de ``SecretsBackend`` pour récupérer des secrets depuis
HashiCorp Vault. Utilise l'API REST directe (httpx) pour éviter la
dépendance ``hvac`` qui est synchrone-only.

Supporte le moteur **KV v2** par défaut (l'API la plus répandue). Pour
KV v1, passer ``kv_version=1`` au constructeur.

Authentification via le header ``X-Vault-Token``.

Structure API KV v2 :
- GET ``{addr}/v1/{mount}/data/{path}`` → retourne ``{"data": {"data": {...}}}``
- Le secret stocké est un objet JSON, on extrait la clé ``value`` par défaut
  (convention GEGM pour les secrets simples string)

Documentation : https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2
"""

import httpx
from loguru import logger

from app.core.secrets.interface import SecretsBackend

_HTTP_TIMEOUT: float = 10.0


class VaultSecretsBackend(SecretsBackend):
    """Récupération de secrets depuis HashiCorp Vault.

    Convention de stockage pour cette intégration : chaque secret est
    stocké comme un objet KV ``{"value": "<la valeur>"}`` au chemin
    ``{mount}/{key}``. Cela permet de garder l'interface ``get(key) -> str``
    simple même si Vault supporte des objets arbitraires.

    Args:
        addr: URL de base de Vault (ex. ``https://vault.example.com``).
        token: Token Vault (root token, AppRole token, Kubernetes auth token).
        mount_path: Chemin du moteur KV monté (``secret`` par défaut).
        kv_version: Version du moteur KV (1 ou 2). Défaut : 2.
    """

    def __init__(
        self,
        addr: str,
        token: str,
        mount_path: str = "secret",
        kv_version: int = 2,
    ) -> None:
        if not addr:
            raise ValueError("VaultSecretsBackend : addr ne peut pas être vide")
        if not token:
            raise ValueError("VaultSecretsBackend : token ne peut pas être vide")
        if kv_version not in (1, 2):
            raise ValueError(
                f"VaultSecretsBackend : kv_version doit être 1 ou 2, reçu {kv_version}",
            )

        self._addr = addr.rstrip("/")
        self._token = token
        self._mount_path = mount_path.strip("/")
        self._kv_version = kv_version

    async def get(self, key: str) -> str:
        """Récupère la valeur d'un secret depuis Vault.

        Args:
            key: Chemin du secret sous le mount (ex. ``app/database_url``).

        Returns:
            Valeur du secret extraite du champ ``value`` de l'objet KV.

        Raises:
            KeyError: Si le secret n'existe pas au chemin indiqué.
            RuntimeError: Pour toute autre erreur (token invalide, réseau,
                réponse malformée, champ ``value`` absent).
        """
        url = self._build_url(key)
        headers = {"X-Vault-Token": self._token}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Vault — erreur réseau pour {key} : {err}", key=key, err=str(exc))
            raise RuntimeError(f"Erreur réseau Vault : {exc}") from exc

        if response.status_code == 404:
            raise KeyError(f"Secret introuvable dans Vault : {key}")

        if response.status_code in (401, 403):
            raise RuntimeError("Token Vault invalide ou permissions insuffisantes")

        if response.status_code != 200:
            logger.error(
                "Vault — HTTP {status} pour {key} : {body}",
                status=response.status_code,
                key=key,
                body=response.text[:200],
            )
            raise RuntimeError(
                f"Vault API error {response.status_code} : {response.text[:200]}",
            )

        try:
            payload = response.json()
            data = self._extract_data(payload)
            value = data.get("value")
        except (KeyError, ValueError) as exc:
            logger.error("Vault — réponse malformée pour {key}", key=key)
            raise RuntimeError(f"Réponse Vault malformée : {exc}") from exc

        if value is None:
            raise RuntimeError(f"Secret Vault {key} ne contient pas de champ 'value'")

        return str(value)

    def _build_url(self, key: str) -> str:
        """Construit l'URL d'accès au secret selon la version du moteur KV.

        Args:
            key: Chemin du secret sous le mount.

        Returns:
            URL complète de l'endpoint GET.
        """
        normalized_key = key.strip("/")
        if self._kv_version == 2:
            return f"{self._addr}/v1/{self._mount_path}/data/{normalized_key}"
        return f"{self._addr}/v1/{self._mount_path}/{normalized_key}"

    def _extract_data(self, payload: dict[str, object]) -> dict[str, object]:
        """Extrait le dictionnaire ``data`` de la réponse Vault.

        KV v2 emballe les données dans ``{"data": {"data": {...}, "metadata": ...}}``.
        KV v1 utilise directement ``{"data": {...}}``.

        Args:
            payload: Réponse JSON brute de Vault.

        Returns:
            Dictionnaire de secrets.

        Raises:
            KeyError: Si la structure attendue n'est pas trouvée.
        """
        outer = payload.get("data")
        if not isinstance(outer, dict):
            raise KeyError("Réponse Vault sans champ 'data'")

        if self._kv_version == 2:
            inner = outer.get("data")
            if not isinstance(inner, dict):
                raise KeyError("Réponse Vault KV v2 sans champ 'data.data'")
            return inner

        return outer
