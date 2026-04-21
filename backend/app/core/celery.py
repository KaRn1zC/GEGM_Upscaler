"""Instance Celery pour la file de tâches d'upscaling.

Le broker et le backend de résultats utilisent Redis. La découverte
automatique des tâches parcourt les modules métier listés ci-dessous.

Sentry est initialisé ici (en plus de ``main.py``) pour capturer les
exceptions des workers Celery qui tournent dans un process séparé.
"""

import sentry_sdk
from celery import Celery
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
