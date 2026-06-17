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
    # tâche Beat ``jobs.reaper.reap_stale_jobs``. Reste à 30 min même si un
    # upscale peut désormais tourner des heures : le polling émet un
    # heartbeat (pipeline ``_touch_heartbeat``) qui rafraîchit ``updated_at``
    # toutes les 60 s, donc seul un worker réellement mort franchit ce seuil.
    STALE_JOB_THRESHOLD_MINUTES: int = 30

    # ── Limites d'upload ─────────────────────────────────────────
    # Taille max d'un fichier image uploadé. 300 Mo couvre les TIFF de
    # photo shoot plein format (45-61 MP ≈ 130-200 Mo) avec de la marge.
    # Doit rester cohérent avec la limite mémoire du pod API (le fichier
    # transite en RAM le temps de la validation + upload storage).
    MAX_UPLOAD_SIZE_MB: int = 300
    # Plafond en mégapixels de l'image SOURCE. Garde-fou contre les
    # decompression bombs et borne opérationnelle : 64 MP couvre tous les
    # boîtiers plein format (61 MP max) tout en restant dans le budget
    # temps GPU (durée estimée 120+200xMP, plafonnée par
    # GPU_JOB_TIMEOUT_MAX_S) et la RAM du worker RunPod.
    MAX_INPUT_MEGAPIXELS: int = 64

    # ── Auth ─────────────────────────────────────────────────────
    AUTH_BACKEND: Literal["static_token", "oidc"] = "static_token"
    DEV_AUTH_TOKEN: SecretStr = SecretStr("dev-secret-token-change-me")
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    # OIDC_CLIENT_SECRET n'est pas utilisé pour la validation JWT (JWKS public)
    # ni par le flow PKCE frontend (clients publics). Réservé pour une éventuelle
    # bascule vers introspection RFC 7662 ou flow BFF qui nécessiterait le secret.
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
    # Plafond du timeout dynamique d'un job GPU (6 h). Le timeout effectif
    # est calculé par image (120 s + 200 s/MP, facteur 2 de marge — cf.
    # ``_compute_gpu_timeout``) puis borné entre 600 s et cette valeur.
    # Couvre le pire cas (64 MP en DRCT-L x4 ≈ 3,3 h sur RTX 5090). La même
    # valeur part en ``policy.executionTimeout`` RunPod : l'Execution Timeout
    # de l'endpoint doit être ≥ à ce plafond, sinon RunPod coupe avant nous.
    GPU_JOB_TIMEOUT_MAX_S: int = 21600
    # Achemine l'image source au worker GPU par URL S3 présignée (gros
    # fichiers, contourne la limite de payload RunPod). Désactivable en
    # urgence si le worker déployé ne supporte pas encore `image_url`
    # (rollback) — le pipeline retombe alors sur le base64 inline.
    GPU_INPUT_URL_ENABLED: bool = True

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

# Garde-fou Pillow centralisé : le défaut interne (~179 MP) est remplacé par
# notre plafond métier + marge, pour TOUS les points de décodage PIL du
# process (uploads, create_job, preprocessing) — config.py étant importé
# partout, la protection est cohérente API/worker. Au-delà de 2x le plafond,
# Pillow lève toujours DecompressionBombError (défense en profondeur).
from PIL import Image  # noqa: E402 — import tardif volontaire, après Settings

Image.MAX_IMAGE_PIXELS = settings.MAX_INPUT_MEGAPIXELS * 1_000_000 * 2
