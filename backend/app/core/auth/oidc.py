"""Backend d'authentification OIDC — validation de JWT via JWKS.

Implémentation de ``AuthBackend`` compatible avec tous les fournisseurs
OIDC standards : Google Workspace, Microsoft Entra ID, Authentik, Auth0,
Keycloak, Okta, etc.

Le flux :
1. L'application cliente obtient un JWT ID token / access token auprès
   de l'IdP via le flow OIDC (Authorization Code + PKCE).
2. Elle envoie ce token au backend dans le header ``Authorization: Bearer <jwt>``.
3. ``OIDCAuth.get_current_user`` valide le token :
   - Signature cryptographique vérifiée contre le JWKS publié par l'IdP
   - ``iss`` claim égal à l'issuer configuré
   - ``aud`` claim égal au client_id configuré
   - ``exp`` claim non expiré
4. Si valide, retourne un ``AuthenticatedUser`` avec email/nom extraits des claims.

Les clés JWKS sont mises en cache pendant ``_JWKS_CACHE_TTL`` secondes pour
éviter un appel HTTP à chaque requête authentifiée.
"""

import time
from typing import Any

import httpx
from loguru import logger

from app.core.auth.interface import AuthBackend, AuthenticatedUser

# Durée de cache du JWKS en secondes. Les IdP font normalement tourner leurs
# clés de signature tous les 24h à 30j, donc un cache d'une heure est un bon
# compromis entre fraîcheur et latence.
_JWKS_CACHE_TTL: int = 3600

# Timeout HTTP pour fetcher la discovery + JWKS.
_HTTP_TIMEOUT: float = 10.0


class OIDCAuth(AuthBackend):
    """Authentification par validation JWT OIDC.

    Args:
        issuer: URL de l'IdP (ex. ``https://accounts.google.com``).
        client_id: ID client OIDC (valeur de ``aud`` attendue dans les tokens).
        client_secret: Secret client OIDC. Actuellement non utilisé pour la
            validation (JWKS est publique), mais conservé pour supporter
            ultérieurement l'introspection de token (RFC 7662) si besoin.
    """

    def __init__(self, issuer: str, client_id: str, client_secret: str) -> None:
        if not issuer:
            raise ValueError("OIDCAuth : issuer ne peut pas être vide")
        if not client_id:
            raise ValueError("OIDCAuth : client_id ne peut pas être vide")

        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        # État du cache JWKS (clé publique du trousseau + timestamp de fetch).
        self._jwks_cache: Any = None
        self._jwks_cache_ts: float = 0.0

    async def get_current_user(self, credentials: str) -> AuthenticatedUser:
        """Valide le JWT et retourne l'utilisateur authentifié.

        Args:
            credentials: JWT brut extrait du header ``Authorization: Bearer``.

        Returns:
            Identité de l'utilisateur authentifié, peuplée depuis les claims
            ``sub``, ``email``, ``name``, ``preferred_username``.

        Raises:
            ValueError: Si le token est invalide (signature, issuer, audience,
                expiration) ou si le JWKS ne peut pas être récupéré.
        """
        try:
            from authlib.jose import jwt
            from authlib.jose.errors import JoseError
        except ImportError as exc:
            raise ImportError(
                "OIDCAuth nécessite authlib. Installer avec : uv add authlib"
            ) from exc

        jwks = await self._get_jwks()

        try:
            claims = jwt.decode(
                credentials,
                key=jwks,
                claims_options={
                    "iss": {"essential": True, "value": self._issuer},
                    "aud": {"essential": True, "value": self._client_id},
                    "exp": {"essential": True},
                },
            )
            claims.validate()
        except JoseError as exc:
            logger.warning("JWT OIDC invalide : {err}", err=str(exc))
            raise ValueError(f"Token JWT invalide : {exc}") from exc
        except Exception as exc:
            logger.error("Erreur inattendue lors de la validation JWT : {err}", err=str(exc))
            raise ValueError(f"Erreur de validation JWT : {exc}") from exc

        user_id = str(claims.get("sub", ""))
        if not user_id:
            raise ValueError("Claim 'sub' manquant dans le JWT")

        email = claims.get("email")
        name = claims.get("name") or claims.get("preferred_username")

        return AuthenticatedUser(
            id=user_id,
            email=str(email) if email else None,
            name=str(name) if name else None,
        )

    async def _get_jwks(self) -> Any:
        """Retourne le trousseau JWKS, en le rafraîchissant si expiré.

        Le premier appel fait une double requête HTTP :
        1. GET ``{issuer}/.well-known/openid-configuration`` → récupère l'URL du JWKS
        2. GET ``{jwks_uri}`` → récupère le trousseau JSON Web Keys

        Les appels suivants utilisent le cache tant que ``_JWKS_CACHE_TTL``
        n'est pas écoulé.

        Returns:
            Trousseau ``authlib.jose.JsonWebKey`` prêt pour la vérification.

        Raises:
            ValueError: Si l'IdP est injoignable ou renvoie une erreur.
        """
        now = time.time()
        if self._jwks_cache is not None and (now - self._jwks_cache_ts) < _JWKS_CACHE_TTL:
            return self._jwks_cache

        try:
            from authlib.jose import JsonWebKey
        except ImportError as exc:
            raise ImportError(
                "OIDCAuth nécessite authlib. Installer avec : uv add authlib"
            ) from exc

        discovery_url = f"{self._issuer}/.well-known/openid-configuration"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                disc_response = await client.get(discovery_url)
                disc_response.raise_for_status()
                jwks_uri = disc_response.json().get("jwks_uri")
                if not jwks_uri:
                    raise ValueError(f"Discovery OIDC sans jwks_uri : {discovery_url}")

                jwks_response = await client.get(jwks_uri)
                jwks_response.raise_for_status()
                jwks_data = jwks_response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "Fetch JWKS OIDC échoué — issuer={iss} err={err}",
                iss=self._issuer,
                err=str(exc),
            )
            raise ValueError(f"Impossible de récupérer le JWKS : {exc}") from exc

        self._jwks_cache = JsonWebKey.import_key_set(jwks_data)
        self._jwks_cache_ts = now
        logger.info("JWKS OIDC rafraîchi — issuer={iss}", iss=self._issuer)

        return self._jwks_cache
