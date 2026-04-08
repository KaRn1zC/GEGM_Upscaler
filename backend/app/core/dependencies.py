"""Injection de dépendances FastAPI — factories de backends.

Chaque factory lit le backend actif depuis la configuration et retourne
l'implémentation concrète correspondante. Le code métier ne dépend que
des interfaces abstraites ; changer d'implémentation ne nécessite qu'une
modification du ``.env``.

Example:
    Utilisation dans un routeur ::

        @router.post("/api/uploads")
        async def upload(storage: StorageBackend = Depends(get_storage)): ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.interface import AuthBackend
from app.core.config import settings
from app.core.database import get_db
from app.core.gpu.interface import GPUBackend
from app.core.secrets.interface import SecretsBackend
from app.core.storage.interface import StorageBackend
from app.users.models import User

# Ré-export pour que les routeurs importent tout depuis dependencies.
__all__ = [
    "get_auth",
    "get_current_user",
    "get_db",
    "get_gpu_cloud",
    "get_gpu_local",
    "get_secrets",
    "get_storage",
]

_bearer_scheme = HTTPBearer()


def get_storage() -> StorageBackend:
    """Retourne l'instance du backend de stockage configuré."""
    if settings.STORAGE_BACKEND == "local":
        from app.core.storage.local import LocalStorageBackend

        return LocalStorageBackend(base_path=settings.LOCAL_STORAGE_PATH)

    # settings.STORAGE_BACKEND == "s3"
    from app.core.storage.s3 import S3StorageBackend

    return S3StorageBackend(
        bucket=settings.S3_BUCKET,
        endpoint_url=settings.S3_ENDPOINT_URL,
        access_key=settings.S3_ACCESS_KEY.get_secret_value(),
        secret_key=settings.S3_SECRET_KEY.get_secret_value(),
        region=settings.S3_REGION,
    )


def get_auth() -> AuthBackend:
    """Retourne l'instance du backend d'authentification configuré."""
    if settings.AUTH_BACKEND == "static_token":
        from app.core.auth.static_token import StaticTokenAuth

        return StaticTokenAuth(token=settings.DEV_AUTH_TOKEN.get_secret_value())

    # settings.AUTH_BACKEND == "oidc"
    from app.core.auth.oidc import OIDCAuth

    return OIDCAuth(
        issuer=settings.OIDC_ISSUER,
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET.get_secret_value(),
    )


def get_secrets() -> SecretsBackend:
    """Retourne l'instance du backend de gestion des secrets configuré."""
    if settings.SECRETS_BACKEND == "env":
        from app.core.secrets.env import EnvSecretsBackend

        return EnvSecretsBackend()

    if settings.SECRETS_BACKEND == "infisical":
        from app.core.secrets.infisical import InfisicalSecretsBackend

        return InfisicalSecretsBackend(
            token=settings.INFISICAL_TOKEN.get_secret_value(),
        )

    # settings.SECRETS_BACKEND == "vault"
    from app.core.secrets.vault import VaultSecretsBackend

    return VaultSecretsBackend(
        addr=settings.VAULT_ADDR,
        token=settings.VAULT_TOKEN.get_secret_value(),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    auth: AuthBackend = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authentifie la requête et retourne l'utilisateur DB correspondant.

    Auto-provisionne l'utilisateur en base lors de sa première connexion
    (lookup par email, création si absent).

    Args:
        credentials: Token Bearer extrait du header Authorization.
        auth: Backend d'authentification actif.
        db: Session de base de données.

    Returns:
        Instance ``User`` correspondant à l'identité authentifiée.

    Raises:
        HTTPException: 401 si les credentials sont invalides ou l'email absent.
    """
    try:
        identity = await auth.get_current_user(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    if identity.email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email manquant dans les credentials",
        )

    result = await db.execute(select(User).where(User.email == identity.email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=identity.email, name=identity.name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


def get_gpu_local() -> GPUBackend:
    """Retourne le backend GPU local (Core ML) pour les images <= 5 MP."""
    from app.core.gpu.local_coreml import CoreMLBackend

    return CoreMLBackend()


def get_gpu_cloud() -> GPUBackend:
    """Retourne le backend GPU cloud (RunPod) pour les images > 5 MP."""
    from app.core.gpu.runpod import RunPodBackend

    return RunPodBackend(
        api_key=settings.RUNPOD_API_KEY.get_secret_value(),
        endpoint_id=settings.RUNPOD_ENDPOINT_ID,
    )
