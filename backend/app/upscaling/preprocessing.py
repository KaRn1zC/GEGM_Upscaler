"""Prétraitement et post-traitement des images pour la super-résolution.

Gère les conversions entre les différents formats manipulés dans le
pipeline : bytes bruts ↔ PIL.Image ↔ numpy array normalisé pour
l'inférence.
"""

from io import BytesIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image


def decode_image(image_data: bytes) -> Image.Image:
    """Décode des bytes bruts en objet PIL Image.

    Convertit automatiquement en RGB si l'image est en mode différent
    (RGBA, palette, niveaux de gris, CMYK, etc.).

    Args:
        image_data: Bytes bruts du fichier image (PNG, JPEG, WebP…).

    Returns:
        Image PIL en mode RGB.

    Raises:
        ValueError: Si les données ne correspondent pas à une image valide.
    """
    try:
        img = Image.open(BytesIO(image_data))
        img.load()
    except Exception as exc:
        raise ValueError(f"Impossible de décoder l'image : {exc}") from exc

    if img.mode == "RGBA":
        # Compositing alpha sur fond blanc avant conversion RGB.
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background

    if img.mode != "RGB":
        return img.convert("RGB")

    return img


def image_to_array(img: Image.Image) -> NDArray[np.float32]:
    """Convertit une image PIL en array numpy normalisé [0, 1].

    Args:
        img: Image PIL en mode RGB.

    Returns:
        Array ``(H, W, 3)`` en float32, valeurs dans [0.0, 1.0].
    """
    return np.asarray(img, dtype=np.float32) / 255.0


def array_to_image(arr: NDArray[np.float32]) -> Image.Image:
    """Convertit un array numpy normalisé en image PIL.

    Args:
        arr: Array ``(H, W, 3)`` en float32, valeurs dans [0.0, 1.0].

    Returns:
        Image PIL en mode RGB.
    """
    clipped = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(clipped, mode="RGB")


def encode_image(img: Image.Image, output_format: str = "png") -> bytes:
    """Encode une image PIL en bytes dans le format demandé.

    Args:
        img: Image PIL à encoder.
        output_format: Format de sortie (``png``, ``jpeg``, ``webp``).

    Returns:
        Bytes du fichier image encodé.

    Raises:
        ValueError: Si le format demandé n'est pas supporté.
    """
    fmt = output_format.lower()
    supported = {"png", "jpeg", "webp"}

    if fmt not in supported:
        raise ValueError(f"Format non supporté : {fmt} (supportés : {', '.join(supported)})")

    buffer = BytesIO()
    save_kwargs: dict[str, object] = {}

    if fmt == "jpeg":
        save_kwargs["quality"] = 95
        # JPEG ne supporte pas la transparence.
        if img.mode == "RGBA":
            img = img.convert("RGB")

    if fmt == "webp":
        save_kwargs["quality"] = 95
        save_kwargs["method"] = 6

    img.save(buffer, format=fmt.upper(), **save_kwargs)
    return buffer.getvalue()


def image_to_uint8(arr: NDArray[np.float32]) -> NDArray[np.uint8]:
    """Convertit un array float32 [0, 1] en uint8 [0, 255].

    Args:
        arr: Array en float32 dans [0.0, 1.0].

    Returns:
        Array en uint8 dans [0, 255].
    """
    converted: NDArray[np.uint8] = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return converted


def uint8_to_float(arr: NDArray[np.uint8]) -> NDArray[np.float32]:
    """Convertit un array uint8 [0, 255] en float32 [0, 1].

    Args:
        arr: Array en uint8 dans [0, 255].

    Returns:
        Array en float32 dans [0.0, 1.0].
    """
    return arr.astype(np.float32) / 255.0
