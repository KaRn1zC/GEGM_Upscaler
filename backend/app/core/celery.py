"""Instance Celery pour la file de tâches d'upscaling.

Le broker et le backend de résultats utilisent Redis. La découverte
automatique des tâches parcourt les modules métier listés ci-dessous.

Sentry est initialisé ici (en plus de ``main.py``) pour capturer les
exceptions des workers Celery qui tournent dans un process séparé.

OpenTelemetry : ``init_telemetry`` est appelée au ``worker_process_init``
pour que les spans des tasks Celery (préparation, download, upscale,
save) soient exportés au collector. L'API appelle aussi
``instrument_celery()`` de son côté pour que les ``task.delay()``
propagent leur trace-id au worker — on reconstitue ainsi une trace unique
HTTP → Celery → RunPod → DB.

Un serveur HTTP Prometheus est démarré sur le port 8001 dans chaque worker
via le même signal — expose les compteurs custom de ``app.core.metrics``
pour que VictoriaMetrics puisse les scraper (cf. chart Helm
``worker-service.yaml``).
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
    # Planification Beat. Nécessite le process `celery beat` en plus du
    # worker (voir docker-compose). Les deux tâches sont idempotentes et
    # peuvent tourner en parallèle sans risque.
    beat_schedule={
        # Cleanup quotidien — supprime les jobs plus vieux que la rétention.
        "cleanup-old-jobs-daily": {
            "task": "jobs.cleanup_old_jobs",
            "schedule": 60 * 60 * 24,  # 24h
        },
        # Reaper toutes les 5 min — marque FAILED les jobs processing zombies
        # (cf. ``jobs.reaper`` : seuil configurable via
        # ``STALE_JOB_THRESHOLD_MINUTES``).
        "reap-stale-jobs": {
            "task": "jobs.reap_stale_jobs",
            "schedule": 60 * 5,  # 5 min
        },
    },
)

# Découverte automatique des tâches dans les modules métier. On importe
# explicitement ``reaper`` pour que la tâche Beat soit enregistrée même
# si ``autodiscover_tasks`` rate le module (timing de l'import).
celery_app.autodiscover_tasks(["app.jobs"])
from app.jobs import reaper as _reaper  # noqa: E402, F401


@worker_process_init.connect
def _on_worker_process_init(**_kwargs: object) -> None:
    """Bootstrap OTel + Prometheus dans chaque process worker.

    Celery lance N process workers (``--concurrency``). Chaque worker doit :
    1. Initialiser OTel pour exporter ses spans vers le collector.
    2. Exposer ses métriques custom sur le port 8001 (port interne au
       cluster, scrapé par le ServiceMonitor worker).

    Note : ``start_http_server`` échoue silencieusement si le port est déjà
    pris (ex. 2e process avec ``concurrency=2``) — on log le warning mais
    on ne propage pas l'erreur pour ne pas bloquer le worker.
    """
    from app.core.metrics import start_metrics_server
    from app.core.telemetry import init_telemetry, instrument_celery

    # OTel d'abord — ainsi les logs suivants portent déjà trace_id/span_id.
    init_telemetry(service_name="gegm-upscaler-worker")
    instrument_celery()

    try:
        start_metrics_server(port=8001)
        logger.info("Prometheus metrics server démarré sur 0.0.0.0:8001")
    except OSError as exc:
        logger.warning(
            "Port 8001 déjà utilisé — metrics server non démarré dans ce process ({err})",
            err=str(exc),
        )
