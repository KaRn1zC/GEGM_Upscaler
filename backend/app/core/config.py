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
    # Rétention des fichiers (inputs + outputs) en jours. Les jobs plus
    # anciens que ce seuil sont supprimés par la tâche Celery Beat
    # ``jobs.cleanup.cleanup_old_jobs``.
    STORAGE_RETENTION_DAYS: int = 30
    # Seuil au-delà duquel un job bloqué en PROCESSING (sans update
    # ``updated_at``) est considéré comme zombie et marqué FAILED par la
    # tâche Beat ``jobs.reaper.reap_stale_jobs``. 30 min couvre les pires
    # cold-starts RunPod (~15 min) + une marge de sécurité.
    STALE_JOB_THRESHOLD_MINUTES: int = 30

    # ── Auth ─────────────────────────────────────────────────────
    AUTH_BACKEND: Literal["static_token", "oidc"] = "static_token"
    DEV_AUTH_TOKEN: SecretStr = SecretStr("dev-secret-token-change-me")
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: SecretStr = SecretStr("")

    # ── GPU ─────────────────────────────────────────────────────
    # Legacy : utilisé uniquement par le backend GPU local Core ML (désactivé
    # en v2 cloud-only, cf. SUIVI "Core ML v2 bloqué upstream"). Pour le
    # routage cloud RunPod, voir `backend.app.jobs.service._model_for_scale`
    # qui tranche selon le scale_factor (x4 → drct-l, x2 → hat-l).
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

    # ── Admin ────────────────────────────────────────────────────
    # Liste des emails avec accès aux endpoints `/api/admin/*`. Simple et
    # suffisant pour un outil interne ~50 users — pas besoin d'une table
    # `roles` en DB. En prod, alimentée depuis Vault ou une GitHub Variable.
    ADMIN_EMAILS: list[str] = []

    # ── Monitoring ───────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── OpenTelemetry ────────────────────────────────────────────
    # Nom de service publié dans les spans/metrics (visible dans les
    # traces côté collector). Conserver la convention `<app>-<role>`
    # pour distinguer API et worker dans les traces unifiées.
    OTEL_SERVICE_NAME: str = "gegm-upscaler-api"
    # Endpoint OTLP gRPC du collector. Vide = tracing désactivé (no-op,
    # pas d'overhead). En prod GEGM : pointera sur l'OTel collector
    # interne ou directement VictoriaMetrics OTLP ingest.
    # Ex: "http://otel-collector.monitoring.svc.cluster.local:4317"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    # Insecure = désactive le TLS sur le canal gRPC. À garder `true`
    # pour un collector intra-cluster (trafic interne). `false` si le
    # collector est exposé via un hostname TLS.
    OTEL_EXPORTER_OTLP_INSECURE: bool = True
    # Échantillonnage 10 % par défaut — ajustable selon le volume réel.
    OTEL_TRACES_SAMPLER_RATIO: float = 0.1

    # ── Frontend embarqué ────────────────────────────────────────
    # Chemin absolu vers le dossier `dist/` du frontend Vite. Si renseigné
    # et que le dossier existe, FastAPI sert le SPA sur toutes les routes
    # non-API (fallback `index.html` pour les deep links React Router).
    # Vide → pas de frontend servi (dev local où Vite tourne sur :5173).
    # En prod Docker, positionné à `/app/frontend/dist` par le Dockerfile.
    FRONTEND_DIST: str = ""

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
