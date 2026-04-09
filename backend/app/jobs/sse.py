"""Streaming SSE (Server-Sent Events) de la progression des jobs.

Fournit un générateur async qui produit des événements formatés selon
le protocole SSE (``text/event-stream``). Le flux se termine
automatiquement quand le job atteint un état final ou après un timeout.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger
from redis.asyncio import Redis

from app.jobs.progress import get_current_progress, subscribe_progress

# États terminaux — le stream se ferme après les avoir émis.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

# Intervalle entre les commentaires keepalive (secondes).
_KEEPALIVE_INTERVAL: float = 15.0

# Timeout maximal du stream SSE (secondes).
_STREAM_TIMEOUT: float = 600.0


def _format_sse(event: str, data: dict[str, Any]) -> str:
    """Formate un événement SSE selon la spécification W3C.

    Args:
        event: Type d'événement (progress, completed, error, etc.).
        data: Payload JSON de l'événement.

    Returns:
        Chaîne formatée prête à être envoyée sur le stream.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _event_type_for_status(status: str) -> str:
    """Détermine le type d'événement SSE à partir du statut du job.

    Args:
        status: Statut courant du job.

    Returns:
        Nom de l'événement SSE correspondant.
    """
    match status:
        case "completed":
            return "completed"
        case "failed" | "cancelled":
            return "error"
        case _:
            return "progress"


async def stream_job_progress(
    redis: Redis,
    job_id: str,
    *,
    initial_status: str,
) -> AsyncGenerator[str, None]:
    """Génère un flux SSE de progression pour un job donné.

    Le flux commence par émettre l'état courant depuis Redis (ou un
    événement synthétique basé sur le statut DB si rien n'est encore
    dans Redis). Ensuite, il souscrit au canal Pub/Sub et transmet
    chaque mise à jour en temps réel.

    Le stream se ferme automatiquement :
    - Quand un état terminal est reçu (completed, failed, cancelled).
    - Après ``_STREAM_TIMEOUT`` secondes sans événement terminal.

    Des commentaires keepalive (``: keepalive``) sont envoyés toutes
    les ``_KEEPALIVE_INTERVAL`` secondes pour maintenir la connexion.

    Args:
        redis: Instance Redis connectée.
        job_id: UUID du job (string).
        initial_status: Statut actuel du job en base de données.

    Yields:
        Chaînes formatées SSE (``event: ...\\ndata: ...\\n\\n``).
    """
    # Si le job est déjà dans un état terminal, émettre un seul event et fermer.
    if initial_status in _TERMINAL_STATUSES:
        current = await get_current_progress(redis, job_id)
        data = current or {"job_id": job_id, "status": initial_status, "progress": 1.0}
        yield _format_sse(_event_type_for_status(initial_status), data)
        return

    pubsub = await subscribe_progress(redis, job_id)

    try:
        # Émettre l'état courant avant de commencer l'écoute.
        current = await get_current_progress(redis, job_id)
        if current:
            yield _format_sse(_event_type_for_status(current["status"]), current)
            if current["status"] in _TERMINAL_STATUSES:
                return

        elapsed = 0.0

        while elapsed < _STREAM_TIMEOUT:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=_KEEPALIVE_INTERVAL,
                )
            except TimeoutError:
                # Pas de message dans l'intervalle — envoi d'un keepalive.
                yield ": keepalive\n\n"
                elapsed += _KEEPALIVE_INTERVAL
                continue

            if message is None:
                # get_message a retourné None (pas de message dans le délai interne).
                elapsed += 1.0
                continue

            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            event_type = _event_type_for_status(data.get("status", "processing"))
            yield _format_sse(event_type, data)

            # Réinitialiser le compteur d'elapsed à chaque vrai message.
            elapsed = 0.0

            if data.get("status") in _TERMINAL_STATUSES:
                return

        # Timeout atteint sans état terminal.
        logger.warning("SSE stream timeout pour le job {job_id}", job_id=job_id)
        yield _format_sse(
            "error",
            {
                "job_id": job_id,
                "status": "timeout",
                "error_message": "Le stream de progression a expiré",
            },
        )

    finally:
        await pubsub.aclose()
