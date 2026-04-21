"""Gestion de la progression des jobs via Redis.

Deux mécanismes complémentaires :

- **Clé Redis** (``job:{id}:progress``) : état courant consultable à tout
  moment, avec TTL d'une heure pour l'auto-nettoyage.
- **Pub/Sub** (canal ``job:{id}:events``) : notifications push temps réel
  consommées par l'endpoint SSE.

Côté écriture : les tâches Celery appellent ``publish_progress``.
Côté lecture : le module SSE souscrit via ``subscribe_progress``.
"""

import json
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

# Durée de rétention de la clé de progression (secondes).
PROGRESS_TTL: int = 3600


def _progress_key(job_id: str) -> str:
    """Clé Redis stockant l'état courant d'un job."""
    return f"job:{job_id}:progress"


def _events_channel(job_id: str) -> str:
    """Nom du canal Pub/Sub pour les événements d'un job."""
    return f"job:{job_id}:events"


async def publish_progress(
    redis: Redis,
    job_id: str,
    *,
    status: str,
    progress: float,
    step: str | None = None,
    output_key: str | None = None,
    error_message: str | None = None,
) -> None:
    """Publie une mise à jour de progression dans Redis.

    Met à jour la clé d'état et envoie une notification sur le canal
    Pub/Sub pour que les clients SSE reçoivent l'événement en temps réel.

    Args:
        redis: Instance Redis connectée.
        job_id: UUID du job (sous forme de string).
        status: Statut courant (processing, completed, failed…).
        progress: Avancement de 0.0 à 1.0.
        step: Étape courante du pipeline (validate, preprocess, upscale…).
        output_key: Clé de stockage du résultat (renseigné à la fin).
        error_message: Message d'erreur en cas d'échec.
    """
    payload: dict[str, Any] = {
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

    # Mise à jour atomique de la clé + publication sur le canal.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(_progress_key(job_id), encoded, ex=PROGRESS_TTL)
        pipe.publish(_events_channel(job_id), encoded)
        await pipe.execute()


async def get_current_progress(redis: Redis, job_id: str) -> dict[str, Any] | None:
    """Lit l'état courant de progression d'un job depuis Redis.

    Args:
        redis: Instance Redis connectée.
        job_id: UUID du job.

    Returns:
        Dictionnaire de l'état courant, ou ``None`` si aucune donnée.
    """
    raw = await redis.get(_progress_key(job_id))
    if raw is None:
        return None
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


async def subscribe_progress(redis: Redis, job_id: str) -> PubSub:
    """Souscrit au canal Pub/Sub de progression d'un job.

    L'appelant doit fermer le ``PubSub`` via ``await pubsub.aclose()``
    une fois terminé.

    Args:
        redis: Instance Redis connectée.
        job_id: UUID du job.

    Returns:
        Instance ``PubSub`` souscrite au canal du job.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(_events_channel(job_id))
    return pubsub


async def cleanup_progress(redis: Redis, job_id: str) -> None:
    """Supprime les données de progression d'un job dans Redis.

    Utile après téléchargement du résultat ou nettoyage périodique.

    Args:
        redis: Instance Redis connectée.
        job_id: UUID du job.
    """
    await redis.delete(_progress_key(job_id))
