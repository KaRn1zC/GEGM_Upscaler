"""Tests de l'helper _guess_media_type du router de téléchargement.

Les tests d'intégration HTTP complets sont dans test_jobs.py (qui
nécessite une DB réelle). On se concentre ici sur la logique pure.
"""

from app.jobs.router import _guess_media_type


def test_should_detect_png() -> None:
    """Extension .png → image/png."""
    assert _guess_media_type("image.png") == "image/png"


def test_should_detect_jpeg() -> None:
    """Extensions .jpg et .jpeg → image/jpeg."""
    assert _guess_media_type("photo.jpg") == "image/jpeg"
    assert _guess_media_type("photo.jpeg") == "image/jpeg"


def test_should_detect_webp() -> None:
    """Extension .webp → image/webp."""
    assert _guess_media_type("img.webp") == "image/webp"


def test_should_detect_tiff() -> None:
    """Extensions .tiff et .tif → image/tiff."""
    assert _guess_media_type("scan.tiff") == "image/tiff"
    assert _guess_media_type("scan.tif") == "image/tiff"


def test_should_be_case_insensitive() -> None:
    """Les extensions en majuscules doivent être reconnues."""
    assert _guess_media_type("IMAGE.PNG") == "image/png"
    assert _guess_media_type("PHOTO.JPEG") == "image/jpeg"


def test_should_default_to_png_for_unknown_extension() -> None:
    """Une extension inconnue doit tomber sur image/png par défaut."""
    assert _guess_media_type("file.xyz") == "image/png"


def test_should_handle_no_extension() -> None:
    """Un nom sans extension doit utiliser le fallback."""
    assert _guess_media_type("noext") == "image/png"
