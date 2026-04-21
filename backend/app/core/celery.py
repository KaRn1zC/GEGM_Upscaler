"""Instance Celery pour la file de tâches d'upscaling.

Le broker et le backend de résultats utilisent Redis. La découverte
automatique des tâches parcourt les modules métier listés ci-dessous.

Sentry est initialisé ici (en plus de ``main.py``) pour capturer les
exceptions des workers Celery qui tournent dans un process séparé.

Un serveur HTTP Prometheus est démarré sur le port 8001 dans chaque worker
via le signal ``worker_process_init`` — expose les compteurs custom de
``app.core.metrics`` pour que Prometheus puisse les scraper (cf.
``monitoring/prometheus/prometheus.yml`` job ``gegm-worker``).
"""

import sentry_sdk
from celery import Celery
from celery.signals import worker_process_init
from loguru import logger
from sentry_sdk.integrations.celery import CeleryIntegration

from app.core.config import settings

# Sentry — capture les exceptions des workers Celery.
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1 if settings.is_development else 0.02,
        send_default_pii=False,
    )

celery_app = Celery(
    "gegm_upscaler",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    # Planification Beat : cleanup quotidien à 03:00 UTC (heure creuse).
    # Nécessite le process `celery beat` en plus du worker (voir docker-compose).
    beat_schedule={
        "cleanup-old-jobs-daily": {
            "task": "jobs.cleanup_old_jobs",
            "schedule": 60 * 60 * 24,  # 24h en secondes
        },
    },
)

# Découverte automatique des tâches dans les modules métier.
celery_app.autodiscover_tasks(["app.jobs"])


@worker_process_init.connect
def _start_prometheus_metrics_server(**_kwargs: object) -> None:
    """Démarre un serveur HTTP Prometheus au lancement de chaque worker.

    Celery lance N process workers (``--concurrency``). Chaque worker expose
    ses métriques custom sur le port 8001 (interne au réseau Docker).
    Prometheus scrape ``worker:8001/metrics`` pour les collecter.

    Note : ``start_http_server`` échoue silencieusement si le port est déjà
    pris (ex. deuxième process avec ``concurrency=2``) — on log le warning
    mais on ne propage pas l'erreur pour ne pas bloquer le worker.
    """
    from app.core.metrics import start_metrics_server

    try:
        start_metrics_server(port=8001)
        logger.info("Prometheus metrics server démarré sur 0.0.0.0:8001")
    except OSError as exc:
        logger.warning(
            "Port 8001 déjà utilisé — metrics server non démarré dans ce process ({err})",
            err=str(exc),
        )
