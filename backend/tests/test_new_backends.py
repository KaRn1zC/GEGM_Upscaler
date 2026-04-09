"""Tests des 4 backends d'infrastructure ajoutés en Phase F.

Ces tests valident :
- L'instanciation correcte (paramètres requis, validation des entrées).
- Le respect de l'interface abstraite (héritage, signatures async).
- Le comportement en erreur (credentials manquants, paramètres invalides).

Les tests d'intégration avec de vrais services S3/OIDC/Infisical/Vault
sont hors scope — ils nécessitent un environnement spécifique qui ne
peut pas tourner en CI standard.
"""

import pytest

from app.core.auth.interface import AuthBackend
from app.core.auth.oidc import OIDCAuth
from app.core.secrets.infisical import InfisicalSecretsBackend
from app.core.secrets.interface import SecretsBackend
from app.core.secrets.vault import VaultSecretsBackend
from app.core.storage.interface import StorageBackend
from app.core.storage.s3 import S3StorageBackend

# ──────────────────────────────────────────────────────────────
# S3StorageBackend
# ──────────────────────────────────────────────────────────────


def test_s3_backend_should_implement_storage_interface() -> None:
    """S3StorageBackend doit hériter de StorageBackend."""
    backend = S3StorageBackend(
        bucket="test-bucket",
        endpoint_url="https://example.com",
        access_key="AKIA-test",
        secret_key="secret-test",
        region="auto",
    )
    assert isinstance(backend, StorageBackend)


def test_s3_backend_should_reject_empty_bucket() -> None:
    """Instanciation sans bucket doit lever ValueError."""
    with pytest.raises(ValueError, match="bucket"):
        S3StorageBackend(
            bucket="",
            endpoint_url="https://example.com",
            access_key="key",
            secret_key="secret",
        )


def test_s3_backend_should_reject_missing_credentials() -> None:
    """Instanciation sans access_key ou secret_key doit lever ValueError."""
    with pytest.raises(ValueError, match="access_key"):
        S3StorageBackend(
            bucket="test",
            endpoint_url="",
            access_key="",
            secret_key="secret",
        )

    with pytest.raises(ValueError, match="access_key"):
        S3StorageBackend(
            bucket="test",
            endpoint_url="",
            access_key="key",
            secret_key="",
        )


def test_s3_backend_should_build_client_kwargs_without_endpoint() -> None:
    """Pour AWS S3 standard, endpoint_url est absent des kwargs."""
    backend = S3StorageBackend(
        bucket="test",
        endpoint_url="",  # AWS S3 standard
        access_key="key",
        secret_key="secret",
        region="us-east-1",
    )
    kwargs = backend._client_kwargs()
    assert "endpoint_url" not in kwargs
    assert kwargs["region_name"] == "us-east-1"
    assert kwargs["aws_access_key_id"] == "key"


def test_s3_backend_should_build_client_kwargs_with_r2_endpoint() -> None:
    """Pour Cloudflare R2, endpoint_url est dans les kwargs."""
    backend = S3StorageBackend(
        bucket="test",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        access_key="key",
        secret_key="secret",
    )
    kwargs = backend._client_kwargs()
    assert kwargs["endpoint_url"] == "https://acct.r2.cloudflarestorage.com"


# ──────────────────────────────────────────────────────────────
# OIDCAuth
# ──────────────────────────────────────────────────────────────


def test_oidc_backend_should_implement_auth_interface() -> None:
    """OIDCAuth doit hériter de AuthBackend."""
    backend = OIDCAuth(
        issuer="https://accounts.example.com",
        client_id="client-123",
        client_secret="secret",
    )
    assert isinstance(backend, AuthBackend)


def test_oidc_backend_should_reject_empty_issuer() -> None:
    """Instanciation sans issuer doit lever ValueError."""
    with pytest.raises(ValueError, match="issuer"):
        OIDCAuth(issuer="", client_id="client", client_secret="secret")


def test_oidc_backend_should_reject_empty_client_id() -> None:
    """Instanciation sans client_id doit lever ValueError."""
    with pytest.raises(ValueError, match="client_id"):
        OIDCAuth(issuer="https://idp.example.com", client_id="", client_secret="secret")


def test_oidc_backend_should_normalize_issuer() -> None:
    """Le trailing slash de l'issuer doit être retiré."""
    backend = OIDCAuth(
        issuer="https://accounts.example.com/",
        client_id="client-123",
        client_secret="secret",
    )
    assert backend._issuer == "https://accounts.example.com"


async def test_oidc_backend_should_reject_invalid_token() -> None:
    """Un token bidon doit être rejeté (erreur réseau sur JWKS fetch)."""
    backend = OIDCAuth(
        issuer="http://127.0.0.1:1",  # port fermé, garantit un échec réseau
        client_id="client-123",
        client_secret="secret",
    )
    with pytest.raises(ValueError):
        await backend.get_current_user("fake-jwt-token")


# ──────────────────────────────────────────────────────────────
# InfisicalSecretsBackend
# ──────────────────────────────────────────────────────────────


def test_infisical_backend_should_implement_secrets_interface() -> None:
    """InfisicalSecretsBackend doit hériter de SecretsBackend."""
    backend = InfisicalSecretsBackend(token="st.dummy.token")
    assert isinstance(backend, SecretsBackend)


def test_infisical_backend_should_reject_empty_token() -> None:
    """Instanciation sans token doit lever ValueError."""
    with pytest.raises(ValueError, match="token"):
        InfisicalSecretsBackend(token="")


def test_infisical_backend_should_accept_optional_project_id() -> None:
    """Le project_id est optionnel et supporté s'il est fourni."""
    backend = InfisicalSecretsBackend(
        token="st.dummy.token",
        project_id="proj-abc",
        environment="staging",
        api_url="https://infisical.example.com/api/",
    )
    assert backend._project_id == "proj-abc"
    assert backend._environment == "staging"
    # Le trailing slash doit être retiré.
    assert backend._api_url == "https://infisical.example.com/api"


async def test_infisical_backend_should_raise_on_unreachable_host() -> None:
    """Un host injoignable doit remonter une RuntimeError (erreur réseau)."""
    backend = InfisicalSecretsBackend(
        token="st.dummy.token",
        api_url="http://127.0.0.1:1",  # port fermé
    )
    with pytest.raises(RuntimeError, match="réseau"):
        await backend.get("SOME_KEY")


# ──────────────────────────────────────────────────────────────
# VaultSecretsBackend
# ──────────────────────────────────────────────────────────────


def test_vault_backend_should_implement_secrets_interface() -> None:
    """VaultSecretsBackend doit hériter de SecretsBackend."""
    backend = VaultSecretsBackend(
        addr="https://vault.example.com",
        token="hvs.dummy",
    )
    assert isinstance(backend, SecretsBackend)


def test_vault_backend_should_reject_empty_addr() -> None:
    """Instanciation sans addr doit lever ValueError."""
    with pytest.raises(ValueError, match="addr"):
        VaultSecretsBackend(addr="", token="hvs.dummy")


def test_vault_backend_should_reject_empty_token() -> None:
    """Instanciation sans token doit lever ValueError."""
    with pytest.raises(ValueError, match="token"):
        VaultSecretsBackend(addr="https://vault.example.com", token="")


def test_vault_backend_should_reject_invalid_kv_version() -> None:
    """kv_version hors {1, 2} doit lever ValueError."""
    with pytest.raises(ValueError, match="kv_version"):
        VaultSecretsBackend(
            addr="https://vault.example.com",
            token="hvs.dummy",
            kv_version=3,  # type: ignore[arg-type]
        )


def test_vault_backend_should_build_kv_v2_url() -> None:
    """KV v2 utilise le chemin /v1/{mount}/data/{key}."""
    backend = VaultSecretsBackend(
        addr="https://vault.example.com/",  # trailing slash test
        token="hvs.dummy",
        mount_path="secret",
        kv_version=2,
    )
    url = backend._build_url("app/db_password")
    assert url == "https://vault.example.com/v1/secret/data/app/db_password"


def test_vault_backend_should_build_kv_v1_url() -> None:
    """KV v1 utilise le chemin /v1/{mount}/{key}."""
    backend = VaultSecretsBackend(
        addr="https://vault.example.com",
        token="hvs.dummy",
        mount_path="kv",
        kv_version=1,
    )
    url = backend._build_url("app/db_password")
    assert url == "https://vault.example.com/v1/kv/app/db_password"


def test_vault_backend_should_extract_data_kv_v2() -> None:
    """L'extraction de données KV v2 doit naviguer data.data."""
    backend = VaultSecretsBackend(
        addr="https://vault.example.com",
        token="hvs.dummy",
        kv_version=2,
    )
    payload = {"data": {"data": {"value": "super-secret"}, "metadata": {}}}
    data = backend._extract_data(payload)
    assert data == {"value": "super-secret"}


def test_vault_backend_should_extract_data_kv_v1() -> None:
    """L'extraction de données KV v1 doit utiliser data direct."""
    backend = VaultSecretsBackend(
        addr="https://vault.example.com",
        token="hvs.dummy",
        kv_version=1,
    )
    payload = {"data": {"value": "super-secret"}}
    data = backend._extract_data(payload)
    assert data == {"value": "super-secret"}


async def test_vault_backend_should_raise_on_unreachable_host() -> None:
    """Un host injoignable doit remonter une RuntimeError (erreur réseau)."""
    backend = VaultSecretsBackend(
        addr="http://127.0.0.1:1",  # port fermé
        token="hvs.dummy",
    )
    with pytest.raises(RuntimeError, match="réseau"):
        await backend.get("app/secret")
