"""Helpers Redis synchrones pour les workers Celery.

Les workers Celery tournent dans des threads synchrones et ne peuvent pas
partager le pool ``redis.asyncio`` de l'API. Ces fonctions utilisent le
client ``redis.Redis`` standard, créé à la demande dans chaque tâche.

Miroir exact de ``jobs.progress`` (version async) — mêmes clés, mêmes
canaux Pub/Sub, même structure de payload JSON.
"""

import json

from redis import Redis

from app.core.config import settings

# Durée de rétention de la clé de progression (secondes). Doit matcher
# la valeur async ``jobs.progress.PROGRESS_TTL``.
PROGRESS_TTL: int = 3600


def get_sync_redis() -> Redis:
    """Crée un client Redis synchrone pour un worker Celery.

    Créé à chaque tâche pour éviter les problèmes de partage entre workers
    (les threads ont leur propre contexte de connexion).

    Returns:
        Client ``redis.Redis`` synchrone, ``decode_responses=True``.
    """
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish_progress_sync(
    redis: Redis,
    job_id: str,
    *,
    status: str,
    progress: float,
    step: str | None = None,
    output_key: str | None = None,
    error_message: str | None = None,
) -> None:
    """Publie une mise à jour de progression (version sync worker).

    Équivalent synchrone de ``jobs.progress.publish_progress``. Même
    structure de payload que la version async pour que les consommateurs
    SSE reçoivent des événements homogènes.

    Args:
        redis: Client Redis synchrone.
        job_id: UUID du job.
        status: Statut courant du job.
        progress: Avancement de 0.0 à 1.0.
        step: Étape courante du pipeline.
        output_key: Clé du résultat (fin de traitement).
        error_message: Détail de l'erreur éventuelle.
    """
    payload: dict[str, object] = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
    }
    if step is not None:
        payload["step"] = step
    if output_key is not None:
        payload["output_key"] = output_key
    if error_message is not None:
        payload["error_message"] = error_message

    encoded = json.dumps(payload)
    pipe = redis.pipeline(transaction=True)
    pipe.set(f"job:{job_id}:progress", encoded, ex=PROGRESS_TTL)
    pipe.publish(f"job:{job_id}:events", encoded)
    pipe.execute()


def cleanup_progress_sync(redis: Redis, job_id: str) -> None:
    """Supprime la clé de progression Redis après finalisation du job.

    Appelé après completion ou échec pour libérer la mémoire Redis
    explicitement au lieu d'attendre le TTL d'une heure.

    Args:
        redis: Client Redis synchrone.
        job_id: UUID du job.
    """
    redis.delete(f"job:{job_id}:progress")
