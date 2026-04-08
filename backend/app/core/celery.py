"""Instance Celery pour la file de tâches d'upscaling.

Le broker et le backend de résultats utilisent Redis. La découverte
automatique des tâches parcourt les modules métier listés ci-dessous.
"""

from celery import Celery

from app.core.config import settings

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
)

# Découverte automatique des tâches dans les modules métier.
celery_app.autodiscover_tasks(["app.jobs"])
