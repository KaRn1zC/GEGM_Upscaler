"""Tests des helpers du pipeline d'upscaling Celery.

Ne teste pas la tâche Celery complète (qui nécessite DB + Redis réels),
mais les helpers pures qui composent le pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.gpu.interface import GPUJobResult, GPUJobStatus
from app.jobs.tasks import (
    _build_output_key,
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
    with patch("app.jobs.tasks.settings") as mock_settings:
        mock_settings.COREML_MODEL_DIR = "/nonexistent/path"
        assert _try_build_local_backend("drct-l") is None


def test_should_return_none_when_coremltools_missing(tmp_path: object) -> None:
    """Si coremltools est indisponible, le backend local doit retourner None."""
    # Créer un faux fichier modèle pour passer le test d'existence.
    fake_model = tmp_path / "drct-l.mlpackage"  # type: ignore[attr-defined]
    fake_model.touch()

    with (
        patch("app.jobs.tasks.settings") as mock_settings,
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
    with patch("app.jobs.tasks.settings") as mock_settings:
        mock_settings.RUNPOD_API_KEY.get_secret_value.return_value = ""
        mock_settings.RUNPOD_ENDPOINT_ID = ""
        assert _try_build_cloud_backend() is None


def test_should_build_runpod_backend_when_configured() -> None:
    """Avec credentials valides, le backend cloud doit être instancié."""
    with patch("app.jobs.tasks.settings") as mock_settings:
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


def test_should_return_none_for_backend_without_output_data_method() -> None:
    """Un backend sans get_output_data doit retourner None (log warning)."""

    class DummyBackend:
        """Backend sans la méthode ``get_output_data``."""

    result = GPUJobResult(status=GPUJobStatus.COMPLETED, progress=1.0)
    assert _extract_output_bytes(DummyBackend(), "job-123", result) is None


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

    # Patch asyncio.sleep pour accélérer le test.
    with (
        patch("app.jobs.tasks.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(TimeoutError, match="n'a pas abouti"),
    ):
        await _wait_for_gpu_result(mock_gpu, "job-123")
