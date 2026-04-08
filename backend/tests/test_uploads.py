"""Tests du module d'upload d'images."""

from io import BytesIO

from httpx import AsyncClient
from PIL import Image

from tests.conftest import AUTH_HEADERS


def _make_test_image(width: int = 100, height: int = 80, fmt: str = "PNG") -> bytes:
    """Crée une image de test en mémoire."""
    img = Image.new("RGB", (width, height), color="red")
    buffer = BytesIO()
    img.save(buffer, format=fmt)
    return buffer.getvalue()


async def test_should_upload_valid_png(client: AsyncClient) -> None:
    """Upload d'un PNG valide retourne 201 avec les métadonnées complètes."""
    content = _make_test_image(200, 150)
    response = await client.post(
        "/api/uploads",
        files={"file": ("photo.png", content, "image/png")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "photo.png"
    assert data["width"] == 200
    assert data["height"] == 150
    assert data["size_bytes"] == len(content)
    assert data["key"].startswith("uploads/")
    assert data["key"].endswith(".png")


async def test_should_upload_valid_jpeg(client: AsyncClient) -> None:
    """Upload d'un JPEG valide retourne 201."""
    content = _make_test_image(300, 200, fmt="JPEG")
    response = await client.post(
        "/api/uploads",
        files={"file": ("photo.jpg", content, "image/jpeg")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 201
    assert response.json()["width"] == 300


async def test_should_reject_non_image_extension(client: AsyncClient) -> None:
    """Un fichier avec une extension non supportée retourne 400."""
    response = await client.post(
        "/api/uploads",
        files={"file": ("document.txt", b"not an image", "text/plain")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert "Format non supporté" in response.json()["detail"]


async def test_should_reject_corrupted_image(client: AsyncClient) -> None:
    """Un fichier avec extension image mais contenu invalide retourne 400."""
    response = await client.post(
        "/api/uploads",
        files={"file": ("fake.png", b"not actually a png", "image/png")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert "corrompu" in response.json()["detail"]


async def test_should_reject_unauthenticated_request(client: AsyncClient) -> None:
    """Un upload sans header Authorization retourne 401."""
    content = _make_test_image()
    response = await client.post(
        "/api/uploads",
        files={"file": ("test.png", content, "image/png")},
    )

    assert response.status_code == 401
