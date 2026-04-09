"""Tests des modules de preprocessing, tiling et CoreMLBackend.

Le modèle Core ML est mocké pour éviter de dépendre d'un fichier
.mlpackage réel et de la plateforme macOS.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.core.gpu.interface import GPUJobStatus, UpscaleParams
from app.core.gpu.local_coreml import CoreMLBackend
from app.upscaling.preprocessing import (
    array_to_image,
    decode_image,
    encode_image,
    image_to_array,
    image_to_uint8,
    uint8_to_float,
)
from app.upscaling.tiling import (
    compute_tile_grid,
    merge_tiles,
    split_into_tiles,
)


def _make_png_bytes(width: int = 64, height: int = 64, color: str = "red") -> bytes:
    """Crée des bytes PNG à partir d'une image PIL de couleur unie.

    Args:
        width: Largeur de l'image.
        height: Hauteur de l'image.
        color: Couleur de remplissage.

    Returns:
        Bytes du fichier PNG.
    """
    img = Image.new("RGB", (width, height), color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


# ──────────────────────────────────────────────────────────────
# Preprocessing
# ──────────────────────────────────────────────────────────────


def test_should_decode_png_to_rgb() -> None:
    """Un PNG RGB doit être décodé en image RGB."""
    data = _make_png_bytes()
    img = decode_image(data)
    assert img.mode == "RGB"
    assert img.size == (64, 64)


def test_should_convert_rgba_to_rgb() -> None:
    """Un PNG RGBA doit être converti en RGB (fond blanc)."""
    img = Image.new("RGBA", (32, 32), (255, 0, 0, 128))
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    result = decode_image(buffer.getvalue())
    assert result.mode == "RGB"


def test_should_convert_grayscale_to_rgb() -> None:
    """Une image en niveaux de gris doit être convertie en RGB."""
    img = Image.new("L", (32, 32), 128)
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    result = decode_image(buffer.getvalue())
    assert result.mode == "RGB"


def test_should_raise_on_invalid_bytes() -> None:
    """Des bytes invalides doivent lever ValueError."""
    with pytest.raises(ValueError, match="Impossible de décoder"):
        decode_image(b"not an image")


def test_should_convert_image_to_float_array() -> None:
    """La conversion image → array doit normaliser en [0, 1]."""
    img = Image.new("RGB", (4, 4), (255, 0, 128))
    arr = image_to_array(img)

    assert arr.dtype == np.float32
    assert arr.shape == (4, 4, 3)
    assert arr[0, 0, 0] == pytest.approx(1.0)
    assert arr[0, 0, 1] == pytest.approx(0.0)


def test_should_convert_array_to_image() -> None:
    """La conversion array → image doit dénormaliser en uint8."""
    arr = np.full((4, 4, 3), 0.5, dtype=np.float32)
    img = array_to_image(arr)

    assert img.mode == "RGB"
    assert img.size == (4, 4)
    # 0.5 * 255 = 127.5 → 127 ou 128 selon l'arrondi.
    pixel = img.getpixel((0, 0))
    assert all(125 <= c <= 130 for c in pixel)


def test_should_encode_png() -> None:
    """L'encodage PNG doit produire des bytes valides."""
    img = Image.new("RGB", (8, 8), "blue")
    data = encode_image(img, "png")

    # Vérifier que c'est un PNG valide.
    decoded = Image.open(BytesIO(data))
    assert decoded.format == "PNG"


def test_should_encode_jpeg() -> None:
    """L'encodage JPEG doit produire des bytes valides."""
    img = Image.new("RGB", (8, 8), "green")
    data = encode_image(img, "jpeg")

    decoded = Image.open(BytesIO(data))
    assert decoded.format == "JPEG"


def test_should_reject_unsupported_format() -> None:
    """Un format non supporté doit lever ValueError."""
    img = Image.new("RGB", (8, 8))
    with pytest.raises(ValueError, match="Format non supporté"):
        encode_image(img, "bmp")


def test_should_roundtrip_uint8_float() -> None:
    """Le cycle uint8 → float → uint8 doit être sans perte."""
    original = np.array([0, 128, 255], dtype=np.uint8)
    roundtrip = image_to_uint8(uint8_to_float(original))
    np.testing.assert_array_equal(original, roundtrip)


# ──────────────────────────────────────────────────────────────
# Tiling
# ──────────────────────────────────────────────────────────────


def test_should_compute_single_tile_for_small_image() -> None:
    """Une image plus petite que tile_size ne produit qu'une tuile."""
    grid = compute_tile_grid(100, 80, tile_size=256, overlap=16)
    assert len(grid) == 1
    assert grid[0] == (0, 0, 100, 80)


def test_should_compute_grid_with_overlap() -> None:
    """La grille doit couvrir l'intégralité de l'image."""
    grid = compute_tile_grid(500, 300, tile_size=256, overlap=32)

    # Vérifier que chaque pixel est couvert.
    covered_x = set()
    covered_y = set()
    for x, y, w, h in grid:
        covered_x.update(range(x, x + w))
        covered_y.update(range(y, y + h))

    assert max(covered_x) >= 499
    assert max(covered_y) >= 299


def test_should_reject_invalid_tile_size() -> None:
    """Un tile_size ≤ 0 doit lever ValueError."""
    with pytest.raises(ValueError, match="tile_size"):
        compute_tile_grid(100, 100, tile_size=0, overlap=0)


def test_should_reject_overlap_exceeding_tile_size() -> None:
    """Un overlap ≥ tile_size doit lever ValueError."""
    with pytest.raises(ValueError, match="overlap"):
        compute_tile_grid(100, 100, tile_size=64, overlap=64)


def test_should_split_and_merge_without_loss() -> None:
    """Split + merge sans traitement doit redonner l'image originale."""
    rng = np.random.default_rng(42)
    original = rng.integers(0, 256, (200, 300, 3), dtype=np.uint8)

    tiles = split_into_tiles(original, tile_size=128, overlap=16)
    assert len(tiles) > 1

    merged = merge_tiles(tiles, output_width=300, output_height=200, overlap=16)

    # Tolérance de 1 à cause du blending float → uint8.
    np.testing.assert_allclose(original.astype(float), merged.astype(float), atol=1.5)


def test_should_handle_exact_tile_size() -> None:
    """Une image de taille exacte = tile_size ne produit qu'une tuile."""
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    tiles = split_into_tiles(arr, tile_size=64, overlap=8)
    assert len(tiles) == 1


# ──────────────────────────────────────────────────────────────
# CoreMLBackend
# ──────────────────────────────────────────────────────────────


def _mock_coreml_model(scale_factor: int = 4) -> MagicMock:
    """Crée un mock de modèle Core ML qui simule un upscale.

    Le mock multiplie les dimensions spatiales par le facteur donné
    en renvoyant un tenseur de la bonne taille rempli de valeurs fixes.

    Args:
        scale_factor: Facteur de multiplication.

    Returns:
        Mock qui se comporte comme un ``coremltools.models.MLModel``.
    """
    model = MagicMock()

    def fake_predict(inputs: dict) -> dict:
        tensor = inputs["input"]
        _, c, h, w = tensor.shape
        output = np.full(
            (1, c, h * scale_factor, w * scale_factor),
            0.5,
            dtype=np.float32,
        )
        return {"output": output}

    model.predict = fake_predict
    return model


async def test_should_submit_and_complete_coreml_job() -> None:
    """Un job Core ML doit se compléter et retourner un résultat."""
    backend = CoreMLBackend(model_path="fake/model.mlpackage")
    image_data = _make_png_bytes(32, 32)

    with patch(
        "app.core.gpu.local_coreml._load_model",
        return_value=_mock_coreml_model(),
    ):
        job_id = await backend.submit_job(image_data, UpscaleParams())

    assert job_id.startswith("coreml-")

    result = await backend.get_job_status(job_id)
    assert result.status == GPUJobStatus.COMPLETED
    assert result.progress == 1.0


async def test_should_produce_valid_output_data() -> None:
    """L'image de sortie doit être un PNG valide."""
    backend = CoreMLBackend(model_path="fake/model.mlpackage")
    image_data = _make_png_bytes(32, 32)

    with patch(
        "app.core.gpu.local_coreml._load_model",
        return_value=_mock_coreml_model(),
    ):
        job_id = await backend.submit_job(image_data, UpscaleParams())

    output = backend.get_output_data(job_id)
    assert output is not None

    # Vérifier que c'est un PNG valide et upscalé x4.
    img = Image.open(BytesIO(output))
    assert img.size == (32 * 4, 32 * 4)


async def test_should_handle_inference_failure() -> None:
    """Une erreur d'inférence doit marquer le job comme FAILED."""
    backend = CoreMLBackend(model_path="fake/model.mlpackage")
    image_data = _make_png_bytes(16, 16)

    failing_model = MagicMock()
    failing_model.predict.side_effect = RuntimeError("CUDA OOM")

    with patch(
        "app.core.gpu.local_coreml._load_model",
        return_value=failing_model,
    ):
        job_id = await backend.submit_job(image_data, UpscaleParams())

    result = await backend.get_job_status(job_id)
    assert result.status == GPUJobStatus.FAILED
    assert result.error is not None


async def test_should_return_failed_for_unknown_job() -> None:
    """Un job inconnu doit retourner FAILED."""
    backend = CoreMLBackend(model_path="fake/model.mlpackage")
    result = await backend.get_job_status("nonexistent")
    assert result.status == GPUJobStatus.FAILED
