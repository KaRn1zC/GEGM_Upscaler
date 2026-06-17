"""Tests des helpers du pipeline d'upscaling Celery.

Ne teste pas la tâche Celery complète (qui nécessite DB + Redis réels),
mais les helpers pures qui composent le pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.gpu.interface import GPUJobResult, GPUJobStatus
from app.upscaling.pipeline import (
    _build_output_key,
    _compute_gpu_timeout,
    _extract_output_bytes,
    _try_build_cloud_backend,
    _try_build_local_backend,
    _wait_for_gpu_result,
)

# ──────────────────────────────────────────────────────────────
# _build_output_key
# ──────────────────────────────────────────────────────────────


def test_should_replace_uploads_prefix_with_results() -> None:
    """Une clé ``uploads/xxx`` doit devenir ``results/xxx``."""
    assert _build_output_key("uploads/abc.png") == "results/abc.png"


def test_should_prepend_results_for_unprefixed_key() -> None:
    """Une clé sans préfixe reçoit ``results/`` en tête."""
    assert _build_output_key("image.png") == "results/image.png"


def test_should_replace_only_first_occurrence() -> None:
    """Seule la première occurrence de ``uploads/`` est remplacée."""
    # Cas pathologique : le nom de fichier contient 'uploads/' — mais
    # replace(..., 1) garantit qu'on ne touche qu'au préfixe.
    assert _build_output_key("uploads/uploads-data.png") == "results/uploads-data.png"


# ──────────────────────────────────────────────────────────────
# _try_build_local_backend
# ──────────────────────────────────────────────────────────────


def test_should_return_none_when_model_file_missing() -> None:
    """Sans fichier modèle, le backend local doit retourner None."""
    with patch("app.upscaling.pipeline.settings") as mock_settings:
        mock_settings.COREML_MODEL_DIR = "/nonexistent/path"
        assert _try_build_local_backend("drct-l") is None


def test_should_return_none_when_coremltools_missing(tmp_path: object) -> None:
    """Si coremltools est indisponible, le backend local doit retourner None."""
    # Créer un faux fichier modèle pour passer le test d'existence.
    fake_model = tmp_path / "drct-l.mlpackage"  # type: ignore[attr-defined]
    fake_model.touch()

    with (
        patch("app.upscaling.pipeline.settings") as mock_settings,
        patch(
            "app.core.gpu.local_coreml.CoreMLBackend",
            side_effect=ImportError("no coremltools"),
        ),
    ):
        mock_settings.COREML_MODEL_DIR = str(tmp_path)  # type: ignore[attr-defined]
        assert _try_build_local_backend("drct-l") is None


# ──────────────────────────────────────────────────────────────
# _try_build_cloud_backend
# ──────────────────────────────────────────────────────────────


def test_should_return_none_without_runpod_credentials() -> None:
    """Sans clé API ou endpoint ID, le backend cloud doit retourner None."""
    # La construction vit dans la factory partagée (cf. _try_build_cloud_backend
    # qui y délègue) — on patche donc les settings lus par la factory.
    with patch("app.core.gpu.factory.settings") as mock_settings:
        mock_settings.RUNPOD_API_KEY.get_secret_value.return_value = ""
        mock_settings.RUNPOD_ENDPOINT_ID = ""
        assert _try_build_cloud_backend() is None


def test_should_build_runpod_backend_when_configured() -> None:
    """Avec credentials valides, le backend cloud doit être instancié."""
    with patch("app.core.gpu.factory.settings") as mock_settings:
        mock_settings.RUNPOD_API_KEY.get_secret_value.return_value = "test-key"
        mock_settings.RUNPOD_ENDPOINT_ID = "test-endpoint"

        backend = _try_build_cloud_backend()
        assert backend is not None


# ──────────────────────────────────────────────────────────────
# _extract_output_bytes
# ──────────────────────────────────────────────────────────────


def test_should_extract_bytes_from_local_backend() -> None:
    """Un backend avec get_output_data doit retourner ses bytes."""
    fake_bytes = b"fake-png-data"
    mock_backend = MagicMock()
    mock_backend.get_output_data.return_value = fake_bytes

    result = GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0)
    assert _extract_output_bytes(mock_backend, "job-123", result) == fake_bytes


def test_should_return_none_for_unknown_job_id() -> None:
    """Un backend doit retourner None pour un job_id inconnu."""
    mock_backend = MagicMock()
    mock_backend.get_output_data.return_value = None

    result = GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0)
    assert _extract_output_bytes(mock_backend, "unknown-job", result) is None


# ──────────────────────────────────────────────────────────────
# _wait_for_gpu_result
# ──────────────────────────────────────────────────────────────


async def test_should_return_immediately_on_completed() -> None:
    """Un job déjà complété doit être retourné sans attente."""
    completed = GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0)

    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(return_value=completed)

    result = await _wait_for_gpu_result(mock_gpu, "job-123")
    assert result.status == GPUJobStatus.COMPLETED
    mock_gpu.get_job_status.assert_called_once()


async def test_should_poll_until_completion() -> None:
    """Le polling doit répéter jusqu'à ce que le statut soit terminal."""
    responses = [
        GPUJobResult(status=GPUJobStatus.QUEUED, progress=0.0),
        GPUJobResult(status=GPUJobStatus.PROCESSING, progress=0.5),
        GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0),
    ]

    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(side_effect=responses)

    result = await _wait_for_gpu_result(mock_gpu, "job-123")
    assert result.status == GPUJobStatus.COMPLETED
    assert mock_gpu.get_job_status.call_count == 3


async def test_should_return_failed_without_retry() -> None:
    """Un job FAILED doit arrêter le polling immédiatement."""
    failed = GPUJobResult(status=GPUJobStatus.FAILED, error="OOM")

    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(return_value=failed)

    result = await _wait_for_gpu_result(mock_gpu, "job-123")
    assert result.status == GPUJobStatus.FAILED
    assert result.error == "OOM"


async def test_should_raise_on_timeout() -> None:
    """Si le job ne se termine pas, un TimeoutError doit être levé."""
    stuck = GPUJobResult(status=GPUJobStatus.PROCESSING, progress=0.5)

    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(return_value=stuck)
    mock_gpu.cancel_job = AsyncMock()

    # Patch asyncio.sleep pour accélérer le test.
    with (
        patch("app.upscaling.pipeline.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(TimeoutError, match="n'a pas abouti"),
    ):
        await _wait_for_gpu_result(mock_gpu, "job-123")

    # Le job provider doit être annulé pour ne pas tourner orphelin facturé.
    mock_gpu.cancel_job.assert_awaited_once_with("job-123")


async def test_should_heartbeat_on_non_terminal_ticks() -> None:
    """Le heartbeat est émis à chaque tick non terminal (anti-reaper sur les
    jobs longs) et jamais après un statut terminal."""
    responses = [
        GPUJobResult(status=GPUJobStatus.QUEUED, progress=0.0),
        GPUJobResult(status=GPUJobStatus.PROCESSING, progress=0.5),
        GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0),
    ]
    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(side_effect=responses)
    heartbeat = AsyncMock()

    with patch("app.upscaling.pipeline.asyncio.sleep", new_callable=AsyncMock):
        result = await _wait_for_gpu_result(
            mock_gpu, "job-123", on_heartbeat=heartbeat, heartbeat_interval_s=0.0
        )

    assert result.status == GPUJobStatus.COMPLETED
    # QUEUED + PROCESSING = 2 ticks non terminaux → 2 heartbeats, rien après COMPLETED.
    assert heartbeat.await_count == 2


async def test_should_survive_heartbeat_failure() -> None:
    """Une erreur du heartbeat est avalée : le polling continue et le job
    aboutit quand même."""
    responses = [
        GPUJobResult(status=GPUJobStatus.PROCESSING, progress=0.5),
        GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0),
    ]
    mock_gpu = MagicMock()
    mock_gpu.get_job_status = AsyncMock(side_effect=responses)
    heartbeat = AsyncMock(side_effect=RuntimeError("DB indisponible"))

    with patch("app.upscaling.pipeline.asyncio.sleep", new_callable=AsyncMock):
        result = await _wait_for_gpu_result(
            mock_gpu, "job-123", on_heartbeat=heartbeat, heartbeat_interval_s=0.0
        )

    assert result.status == GPUJobStatus.COMPLETED
    heartbeat.assert_awaited()


# ──────────────────────────────────────────────────────────────
# _compute_gpu_timeout
# ──────────────────────────────────────────────────────────────


def test_should_floor_gpu_timeout_at_ten_minutes() -> None:
    """Une petite image garde le plancher historique de 600 s."""
    assert _compute_gpu_timeout(0.5) == 600


def test_should_scale_gpu_timeout_with_megapixels() -> None:
    """Le timeout suit la formule 2 x (120 + 200/MP) au-delà du plancher."""
    # 20 MP : 2 x (120 + 4000) = 8240 s — sous le plafond de 21600 s.
    assert _compute_gpu_timeout(20.0) == 8240


def test_should_cap_gpu_timeout_at_settings_max() -> None:
    """Une image énorme est bornée par GPU_JOB_TIMEOUT_MAX_S."""
    assert _compute_gpu_timeout(500.0) == settings.GPU_JOB_TIMEOUT_MAX_S
