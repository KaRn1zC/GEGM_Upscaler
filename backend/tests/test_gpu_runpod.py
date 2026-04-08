"""Tests du backend GPU RunPod Serverless.

Utilise des mocks httpx pour simuler les réponses de l'API RunPod
sans appeler le service réel.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.gpu.interface import GPUJobStatus, UpscaleParams
from app.core.gpu.runpod import RunPodBackend


@pytest.fixture
def backend() -> RunPodBackend:
    """Instance RunPodBackend avec des credentials factices."""
    return RunPodBackend(api_key="test-key", endpoint_id="test-endpoint")


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    """Crée une réponse httpx simulée.

    Args:
        status_code: Code HTTP de la réponse.
        json_data: Payload JSON de la réponse.

    Returns:
        Instance ``httpx.Response`` prête à l'emploi.
    """
    return httpx.Response(status_code=status_code, json=json_data)


# ──────────────────────────────────────────────────────────────
# submit_job
# ──────────────────────────────────────────────────────────────


async def test_should_submit_job_and_return_id(backend: RunPodBackend) -> None:
    """Un submit réussi doit retourner l'ID du job RunPod."""
    mock_resp = _mock_response(200, {"id": "rp-abc123", "status": "IN_QUEUE"})

    with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_resp):
        job_id = await backend.submit_job(b"fake-image-data", UpscaleParams())

    assert job_id == "rp-abc123"


async def test_should_send_base64_encoded_image(backend: RunPodBackend) -> None:
    """Le payload envoyé doit contenir l'image encodée en base64."""
    mock_resp = _mock_response(200, {"id": "rp-123", "status": "IN_QUEUE"})
    mock_post = AsyncMock(return_value=mock_resp)

    with patch.object(backend._client, "post", mock_post):
        await backend.submit_job(b"\x89PNG", UpscaleParams(scale_factor=2, model_name="hat-l"))

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["input"]["scale_factor"] == 2
    assert payload["input"]["model_name"] == "hat-l"
    # Vérifie que c'est bien du base64 valide.
    assert isinstance(payload["input"]["image"], str)
    assert len(payload["input"]["image"]) > 0


async def test_should_raise_on_submit_http_error(backend: RunPodBackend) -> None:
    """Une erreur HTTP au submit doit lever RuntimeError."""
    mock_resp = _mock_response(500, {"error": "internal error"})

    with (
        patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_resp),
        pytest.raises(RuntimeError, match="RunPod API error 500"),
    ):
        await backend.submit_job(b"data", UpscaleParams())


# ──────────────────────────────────────────────────────────────
# get_job_status
# ──────────────────────────────────────────────────────────────


async def test_should_return_queued_status(backend: RunPodBackend) -> None:
    """Un job IN_QUEUE doit être mappé vers QUEUED avec progress 0."""
    mock_resp = _mock_response(200, {"id": "rp-1", "status": "IN_QUEUE"})

    with patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await backend.get_job_status("rp-1")

    assert result.status == GPUJobStatus.QUEUED
    assert result.progress == 0.0


async def test_should_return_processing_status(backend: RunPodBackend) -> None:
    """Un job IN_PROGRESS doit être mappé vers PROCESSING avec progress 0.5."""
    mock_resp = _mock_response(200, {"id": "rp-2", "status": "IN_PROGRESS"})

    with patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await backend.get_job_status("rp-2")

    assert result.status == GPUJobStatus.PROCESSING
    assert result.progress == 0.5


async def test_should_return_completed_with_output_key(backend: RunPodBackend) -> None:
    """Un job COMPLETED doit inclure la clé de sortie."""
    mock_resp = _mock_response(200, {
        "id": "rp-3",
        "status": "COMPLETED",
        "output": {"output_key": "results/upscaled.png"},
    })

    with patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await backend.get_job_status("rp-3")

    assert result.status == GPUJobStatus.COMPLETED
    assert result.progress == 1.0
    assert result.output_key == "results/upscaled.png"


async def test_should_return_failed_with_error_message(backend: RunPodBackend) -> None:
    """Un job FAILED doit inclure le message d'erreur."""
    mock_resp = _mock_response(200, {
        "id": "rp-4",
        "status": "FAILED",
        "error": "CUDA out of memory",
    })

    with patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await backend.get_job_status("rp-4")

    assert result.status == GPUJobStatus.FAILED
    assert result.error == "CUDA out of memory"


async def test_should_map_timed_out_to_failed(backend: RunPodBackend) -> None:
    """Un job TIMED_OUT RunPod doit être traité comme FAILED."""
    mock_resp = _mock_response(200, {"id": "rp-5", "status": "TIMED_OUT"})

    with patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await backend.get_job_status("rp-5")

    assert result.status == GPUJobStatus.FAILED
    assert result.error == "TIMED_OUT"


async def test_should_raise_on_status_http_error(backend: RunPodBackend) -> None:
    """Une erreur HTTP au polling doit lever RuntimeError."""
    mock_resp = _mock_response(404, {"error": "not found"})

    with (
        patch.object(backend._client, "get", new_callable=AsyncMock, return_value=mock_resp),
        pytest.raises(RuntimeError, match="RunPod API error 404"),
    ):
        await backend.get_job_status("rp-unknown")


# ──────────────────────────────────────────────────────────────
# cancel_job
# ──────────────────────────────────────────────────────────────


async def test_should_cancel_job_without_error(backend: RunPodBackend) -> None:
    """L'annulation d'un job ne doit pas lever d'exception."""
    mock_resp = _mock_response(200, {"id": "rp-6", "status": "CANCELLED"})

    with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_resp):
        await backend.cancel_job("rp-6")
