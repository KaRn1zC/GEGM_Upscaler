"""Tests du routeur GPU — sélection du backend selon les dimensions."""

from unittest.mock import MagicMock

import pytest

from app.core.gpu.interface import GPUBackend
from app.upscaling.router_gpu import LOCAL_MAX_MEGAPIXELS, compute_megapixels, select_gpu_backend


def _mock_backend(name: str) -> GPUBackend:
    """Crée un mock de GPUBackend identifiable par son nom.

    Args:
        name: Nom attribué au mock pour vérification.

    Returns:
        Mock qui se comporte comme un GPUBackend.
    """
    mock = MagicMock(spec=GPUBackend)
    mock.name = name
    return mock


# ──────────────────────────────────────────────────────────────
# compute_megapixels
# ──────────────────────────────────────────────────────────────


def test_should_compute_megapixels_correctly() -> None:
    """4000x3000 = 12.0 MP."""
    assert compute_megapixels(4000, 3000) == 12.0


def test_should_handle_small_images() -> None:
    """640x480 = 0.3072 MP."""
    assert compute_megapixels(640, 480) == pytest.approx(0.3072)


def test_should_compute_exact_threshold() -> None:
    """Une image de exactement 5 MP (ex: ~2236x2236)."""
    # 2236 * 2236 = 4_999_696 → ~4.999696 MP, juste sous le seuil.
    assert compute_megapixels(2500, 2000) == 5.0


# ──────────────────────────────────────────────────────────────
# select_gpu_backend
# ──────────────────────────────────────────────────────────────


def test_should_route_small_image_to_local() -> None:
    """Une image ≤ 5 MP doit être routée vers le backend local."""
    local = _mock_backend("local")
    cloud = _mock_backend("cloud")

    # 1920x1080 = 2.07 MP → local.
    result = select_gpu_backend(1920, 1080, local_backend=local, cloud_backend=cloud)
    assert result.name == "local"


def test_should_route_large_image_to_cloud() -> None:
    """Une image > 5 MP doit être routée vers le backend cloud."""
    local = _mock_backend("local")
    cloud = _mock_backend("cloud")

    # 4000x3000 = 12 MP → cloud.
    result = select_gpu_backend(4000, 3000, local_backend=local, cloud_backend=cloud)
    assert result.name == "cloud"


def test_should_route_threshold_image_to_local() -> None:
    """Une image de exactement 5 MP (seuil) doit aller en local."""
    local = _mock_backend("local")
    cloud = _mock_backend("cloud")

    # 2500x2000 = 5.0 MP = seuil → local.
    result = select_gpu_backend(2500, 2000, local_backend=local, cloud_backend=cloud)
    assert result.name == "local"


def test_should_fallback_to_cloud_when_local_unavailable() -> None:
    """Sans backend local, une petite image doit quand même être traitée via cloud."""
    cloud = _mock_backend("cloud")

    result = select_gpu_backend(1920, 1080, local_backend=None, cloud_backend=cloud)
    assert result.name == "cloud"


def test_should_fallback_to_local_when_cloud_unavailable() -> None:
    """Sans backend cloud, une grande image doit être traitée en local (plus lent)."""
    local = _mock_backend("local")

    result = select_gpu_backend(4000, 3000, local_backend=local, cloud_backend=None)
    assert result.name == "local"


def test_should_raise_when_no_backend_available() -> None:
    """Sans aucun backend, le routage doit lever RuntimeError."""
    with pytest.raises(RuntimeError, match="Aucun backend GPU disponible"):
        select_gpu_backend(1920, 1080, local_backend=None, cloud_backend=None)


def test_should_use_threshold_from_constant() -> None:
    """Le seuil exposé comme constante doit valoir 5.0 MP."""
    assert LOCAL_MAX_MEGAPIXELS == 5.0
