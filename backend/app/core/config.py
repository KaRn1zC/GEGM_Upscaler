"""Configuration applicative chargée depuis les variables d'environnement.

Utilise pydantic-settings pour valider et typer l'ensemble de la configuration.
Les valeurs sensibles utilisent ``SecretStr`` pour éviter toute fuite dans les logs.
"""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration globale de l'application.

    Toutes les valeurs sont chargées depuis les variables d'environnement
    ou un fichier ``.env``. Les sélecteurs de backend (``STORAGE_BACKEND``,
    ``AUTH_BACKEND``, ``SECRETS_BACKEND``) déterminent quelle implémentation
    concrète est injectée à l'exécution.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Application ──────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    CORS_ORIGINS: list[str] = [
        "http://localhost:1420",  # Tauri dev
        "http://localhost:5173",  # Vite dev
        "tauri://localhost",  # Tauri production
    ]

    # ── Database ─────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://upscaler:upscaler@localhost:5432/upscaler"

    # ── Redis ────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Storage ──────────────────────────────────────────────────
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_PATH: str = "/data"
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: SecretStr = SecretStr("")
    S3_SECRET_KEY: SecretStr = SecretStr("")
    S3_REGION: str = "auto"

    # ── Auth ─────────────────────────────────────────────────────
    AUTH_BACKEND: Literal["static_token", "oidc"] = "static_token"
    DEV_AUTH_TOKEN: SecretStr = SecretStr("dev-secret-token-change-me")
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: SecretStr = SecretStr("")

    # ── GPU ─────────────────────────────────────────────────────
    UPSCALE_MODEL: Literal["drct-l", "hat-l"] = "drct-l"
    COREML_MODEL_DIR: str = "models"
    RUNPOD_API_KEY: SecretStr = SecretStr("")
    RUNPOD_ENDPOINT_ID: str = ""

    # ── Stockage S3 des outputs RunPod ─────────────────────────
    # Le handler RunPod upload les images upscalées sur ce bucket car l'API
    # /status de RunPod est limitée à ~20 MB de payload. Si les 4 variables
    # sont renseignées, le backend télécharge depuis ce bucket ; sinon il
    # fallback sur le base64 inline.
    S3_OUTPUT_ENDPOINT_URL: str = ""
    S3_OUTPUT_BUCKET: str = ""
    S3_OUTPUT_ACCESS_KEY: SecretStr = SecretStr("")
    S3_OUTPUT_SECRET_KEY: SecretStr = SecretStr("")
    S3_OUTPUT_REGION: str = "auto"

    # ── Monitoring ───────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Secrets ──────────────────────────────────────────────────
    SECRETS_BACKEND: Literal["env", "infisical", "vault"] = "env"
    # Infisical : un seul token suffit en SaaS, project_id et environment
    # permettent de cibler un workspace et un env spécifiques.
    INFISICAL_TOKEN: SecretStr = SecretStr("")
    INFISICAL_PROJECT_ID: str = ""
    INFISICAL_ENVIRONMENT: str = "prod"
    INFISICAL_API_URL: str = "https://app.infisical.com/api"
    # Vault : addr + token + chemin du mount KV. KV v2 par défaut.
    VAULT_ADDR: str = ""
    VAULT_TOKEN: SecretStr = SecretStr("")
    VAULT_MOUNT_PATH: str = "secret"
    VAULT_KV_VERSION: Literal[1, 2] = 2

    @property
    def is_development(self) -> bool:
        """Indique si l'application tourne en mode développement."""
        return self.APP_ENV == "development"


settings = Settings()
