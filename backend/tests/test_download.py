"""Tests de l'helper guess_media_type partagé.

Les tests d'intégration HTTP complets sont dans test_jobs.py (qui
nécessite une DB réelle). On se concentre ici sur la logique pure.
"""

from app.core.media import guess_media_type


def test_should_detect_png() -> None:
    """Extension .png → image/png."""
    assert guess_media_type("image.png") == "image/png"


def test_should_detect_jpeg() -> None:
    """Extensions .jpg et .jpeg → image/jpeg."""
    assert guess_media_type("photo.jpg") == "image/jpeg"
    assert guess_media_type("photo.jpeg") == "image/jpeg"


def test_should_detect_webp() -> None:
    """Extension .webp → image/webp."""
    assert guess_media_type("img.webp") == "image/webp"


def test_should_detect_tiff() -> None:
    """Extensions .tiff et .tif → image/tiff."""
    assert guess_media_type("scan.tiff") == "image/tiff"
    assert guess_media_type("scan.tif") == "image/tiff"


def test_should_be_case_insensitive() -> None:
    """Les extensions en majuscules doivent être reconnues."""
    assert guess_media_type("IMAGE.PNG") == "image/png"
    assert guess_media_type("PHOTO.JPEG") == "image/jpeg"


def test_should_default_to_png_for_unknown_extension() -> None:
    """Une extension inconnue doit tomber sur image/png par défaut."""
    assert guess_media_type("file.xyz") == "image/png"


def test_should_handle_no_extension() -> None:
    """Un nom sans extension doit utiliser le fallback."""
    assert guess_media_type("noext") == "image/png"
