"""Tests du streaming SSE de progression des jobs.

Utilise fakeredis pour simuler Redis sans service externe, et vérifie
le comportement de l'endpoint SSE et des fonctions de progression.
"""

import asyncio
import json

import fakeredis.aioredis
import pytest

from app.jobs.progress import (
    cleanup_progress,
    get_current_progress,
    publish_progress,
    subscribe_progress,
)
from app.jobs.sse import _format_sse, stream_job_progress


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    """Instance fakeredis async pour les tests sans serveur Redis réel."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ──────────────────────────────────────────────────────────────
# Tests du module progress
# ──────────────────────────────────────────────────────────────


async def test_should_publish_and_read_progress(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """La progression publiée doit être récupérable via la clé Redis."""
    await publish_progress(
        fake_redis,
        "job-123",
        status="processing",
        progress=0.5,
        step="upscale",
    )

    result = await get_current_progress(fake_redis, "job-123")
    assert result is not None
    assert result["status"] == "processing"
    assert result["progress"] == 0.5
    assert result["step"] == "upscale"


async def test_should_return_none_for_unknown_job(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Un job sans progression en Redis doit retourner None."""
    result = await get_current_progress(fake_redis, "nonexistent")
    assert result is None


async def test_should_include_optional_fields(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Les champs optionnels output_key et error_message sont inclus quand fournis."""
    await publish_progress(
        fake_redis,
        "job-456",
        status="completed",
        progress=1.0,
        output_key="results/img.png",
    )

    result = await get_current_progress(fake_redis, "job-456")
    assert result is not None
    assert result["output_key"] == "results/img.png"
    assert "error_message" not in result


async def test_should_publish_to_pubsub_channel(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """La publication doit envoyer un message sur le canal Pub/Sub."""
    pubsub = await subscribe_progress(fake_redis, "job-789")

    # Consommer le message de souscription.
    await pubsub.get_message(timeout=1.0)

    await publish_progress(
        fake_redis,
        "job-789",
        status="processing",
        progress=0.25,
        step="validate",
    )

    message = await pubsub.get_message(timeout=2.0)
    assert message is not None
    assert message["type"] == "message"

    data = json.loads(message["data"])
    assert data["progress"] == 0.25
    assert data["step"] == "validate"

    await pubsub.aclose()


async def test_should_cleanup_progress_data(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Le nettoyage doit supprimer la clé de progression."""
    await publish_progress(
        fake_redis,
        "job-cleanup",
        status="completed",
        progress=1.0,
    )

    await cleanup_progress(fake_redis, "job-cleanup")
    result = await get_current_progress(fake_redis, "job-cleanup")
    assert result is None


# ──────────────────────────────────────────────────────────────
# Tests du module SSE
# ──────────────────────────────────────────────────────────────


def test_should_format_sse_event() -> None:
    """Le formatage SSE doit respecter la spécification W3C."""
    result = _format_sse("progress", {"progress": 0.5})
    assert result == 'event: progress\ndata: {"progress": 0.5}\n\n'


async def test_should_emit_single_event_for_completed_job(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Un job déjà terminé doit émettre un seul événement puis fermer le stream."""
    await publish_progress(
        fake_redis,
        "job-done",
        status="completed",
        progress=1.0,
        output_key="results/out.png",
    )

    events: list[str] = []
    async for event in stream_job_progress(fake_redis, "job-done", initial_status="completed"):
        events.append(event)

    assert len(events) == 1
    assert "completed" in events[0]


async def test_should_emit_single_event_for_failed_job(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Un job en échec doit émettre un événement error puis fermer."""
    events: list[str] = []
    async for event in stream_job_progress(fake_redis, "job-fail", initial_status="failed"):
        events.append(event)

    assert len(events) == 1
    assert "error" in events[0]


async def test_should_stream_progress_updates(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Le stream doit transmettre les mises à jour publiées dans Redis."""
    events: list[str] = []

    async def _publisher() -> None:
        """Publie des événements de progression avec un léger délai."""
        await asyncio.sleep(0.1)
        await publish_progress(
            fake_redis, "job-stream", status="processing", progress=0.5, step="upscale"
        )
        await asyncio.sleep(0.1)
        await publish_progress(
            fake_redis, "job-stream", status="completed", progress=1.0, step="done"
        )

    async def _consumer() -> None:
        """Consomme le stream SSE."""
        async for event in stream_job_progress(
            fake_redis, "job-stream", initial_status="processing"
        ):
            events.append(event)
            # Arrêter si on a reçu l'événement terminal.
            if "completed" in event:
                break

    # Lancer éditeur et consommateur en parallèle.
    await asyncio.gather(_publisher(), _consumer())

    # On doit avoir au moins l'événement de complétion.
    completed_events = [e for e in events if "completed" in e]
    assert len(completed_events) >= 1


async def test_should_emit_error_for_cancelled_job(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Un job annulé doit émettre un événement error."""
    events: list[str] = []
    async for event in stream_job_progress(fake_redis, "job-cancel", initial_status="cancelled"):
        events.append(event)

    assert len(events) == 1
    assert "error" in events[0]
    data = json.loads(events[0].split("data: ")[1].strip())
    assert data["status"] == "cancelled"
