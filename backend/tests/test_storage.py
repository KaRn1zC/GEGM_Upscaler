"""Tests du backend de stockage local (filesystem)."""

from io import BytesIO
from pathlib import Path

import pytest

from app.core.storage.local import LocalStorageBackend


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    """Fournit un backend de stockage pointant vers un répertoire temporaire."""
    return LocalStorageBackend(base_path=str(tmp_path))


# ── Upload / Download ────────────────────────────────────────────


async def test_should_upload_and_download_bytes(storage: LocalStorageBackend) -> None:
    """Upload en bytes bruts puis relecture — le contenu doit être identique."""
    key = await storage.upload("photo.png", b"fake image data")

    assert key == "photo.png"
    assert await storage.download(key) == b"fake image data"


async def test_should_upload_binary_stream(storage: LocalStorageBackend) -> None:
    """Upload depuis un flux BinaryIO (simule un UploadFile.file)."""
    stream = BytesIO(b"stream content")
    key = await storage.upload("doc.pdf", stream, content_type="application/pdf")

    assert await storage.download(key) == b"stream content"


async def test_should_create_nested_directories(storage: LocalStorageBackend) -> None:
    """Les sous-répertoires sont créés automatiquement pour les clés imbriquées."""
    key = await storage.upload("uploads/2026/04/photo.jpg", b"nested")

    assert await storage.download(key) == b"nested"


async def test_should_overwrite_existing_file(storage: LocalStorageBackend) -> None:
    """Un deuxième upload sur la même clé écrase le contenu précédent."""
    await storage.upload("file.txt", b"version 1")
    await storage.upload("file.txt", b"version 2")

    assert await storage.download("file.txt") == b"version 2"


# ── Download errors ──────────────────────────────────────────────


async def test_should_raise_on_download_missing_file(
    storage: LocalStorageBackend,
) -> None:
    """Le téléchargement d'une clé inexistante lève FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await storage.download("nonexistent.png")


# ── Delete ───────────────────────────────────────────────────────


async def test_should_delete_file(storage: LocalStorageBackend) -> None:
    """Après suppression, le fichier n'est plus accessible."""
    await storage.upload("temp.bin", b"to delete")
    await storage.delete("temp.bin")

    with pytest.raises(FileNotFoundError):
        await storage.download("temp.bin")


async def test_should_raise_on_delete_missing_file(
    storage: LocalStorageBackend,
) -> None:
    """La suppression d'une clé inexistante lève FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await storage.delete("ghost.bin")


# ── Presigned URL ────────────────────────────────────────────────


async def test_should_return_key_as_presigned_url(
    storage: LocalStorageBackend,
) -> None:
    """En local, l'URL présignée retourne la clé de stockage."""
    await storage.upload("result.png", b"upscaled")
    url = await storage.get_presigned_url("result.png")

    assert url == "result.png"


async def test_should_raise_presigned_url_for_missing_file(
    storage: LocalStorageBackend,
) -> None:
    """L'URL présignée pour un fichier inexistant lève FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await storage.get_presigned_url("missing.png")


# ── Sécurité ─────────────────────────────────────────────────────


async def test_should_block_path_traversal_on_upload(
    storage: LocalStorageBackend,
) -> None:
    """Une clé avec ``../`` est rejetée pour empêcher l'écriture hors périmètre."""
    with pytest.raises(ValueError, match="traversée de chemin"):
        await storage.upload("../../etc/passwd", b"evil")


async def test_should_block_path_traversal_on_download(
    storage: LocalStorageBackend,
) -> None:
    """Une clé avec ``../`` est rejetée pour empêcher la lecture hors périmètre."""
    with pytest.raises(ValueError, match="traversée de chemin"):
        await storage.download("../../../etc/shadow")


async def test_should_block_path_traversal_on_delete(
    storage: LocalStorageBackend,
) -> None:
    """Une clé avec ``../`` est rejetée pour empêcher la suppression hors périmètre."""
    with pytest.raises(ValueError, match="traversée de chemin"):
        await storage.delete("../../important_file")
