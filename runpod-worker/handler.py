"""Handler RunPod Serverless pour l'upscaling GEGM.

Point d'entrée invoqué par RunPod pour chaque job. Reçoit une image
encodée en base64, exécute l'inférence via le modèle DRCT-L (ou HAT-L
en fallback), et retourne l'image upscalée encodée en base64.

Protocole I/O avec le client ``RunPodBackend`` :

Entrée (event["input"]) :
    {
        "image": "<base64 PNG/JPEG>",
        "scale_factor": 2 | 4,
        "model_name": "drct-l" | "hat-l",
        "output_format": "png" | "jpeg" | "webp"
    }

Sortie :
    {
        "image": "<base64 de l'image upscalée>",
        "width": int,
        "height": int,
        "model": str,
        "scale_factor": int
    }

En cas d'erreur, retourne ``{"error": "<message>"}``.
"""

import base64
import io
import os
from pathlib import Path
from typing import Any

import numpy as np
import runpod
import torch
from loguru import logger
from PIL import Image

# Configuration depuis les variables d'environnement.
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "drct-l")
TILE_SIZE = int(os.environ.get("TILE_SIZE", "512"))
TILE_OVERLAP = int(os.environ.get("TILE_OVERLAP", "32"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Cache des modèles chargés (pour éviter de recharger entre les jobs).
_model_cache: dict[str, torch.nn.Module] = {}


def load_model(model_name: str) -> torch.nn.Module:
    """Charge un modèle PyTorch depuis le disque avec cache en mémoire.

    Les poids sont cherchés dans ``MODEL_DIR/{model_name}.pth``.
    Le code d'architecture du modèle doit être disponible (DRCT, HAT).

    Args:
        model_name: Identifiant du modèle (``drct-l``, ``hat-l``).

    Returns:
        Modèle PyTorch en mode inférence, placé sur le bon device.

    Raises:
        FileNotFoundError: Si le fichier de poids n'existe pas.
        ValueError: Si le modèle n'est pas reconnu.
    """
    if model_name in _model_cache:
        return _model_cache[model_name]

    weights_path = MODEL_DIR / f"{model_name}.pth"
    if not weights_path.exists():
        raise FileNotFoundError(f"Poids introuvables : {weights_path}")

    if model_name == "drct-l":
        from drct.archs.DRCT_arch import DRCT
        # DRCT-L : 12 RSTB blocks (vs 6 pour DRCT de base).
        model = DRCT(
            upscale=4,
            in_chans=3,
            img_size=64,
            window_size=16,
            compress_ratio=3,
            squeeze_factor=30,
            conv_scale=0.01,
            overlap_ratio=0.5,
            img_range=1.0,
            depths=[6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
            embed_dim=180,
            num_heads=[6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
            mlp_ratio=2,
            upsampler="pixelshuffle",
            resi_connection="1conv",
        )
    elif model_name == "hat-l":
        from hat.archs.hat_arch import HAT
        # HAT-L : 12 RHAG blocks (vs 6 pour HAT de base).
        model = HAT(
            upscale=4,
            in_chans=3,
            img_size=64,
            window_size=16,
            compress_ratio=3,
            squeeze_factor=30,
            conv_scale=0.01,
            overlap_ratio=0.5,
            img_range=1.0,
            depths=[6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
            embed_dim=180,
            num_heads=[6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
            mlp_ratio=2,
            upsampler="pixelshuffle",
            resi_connection="1conv",
        )
    else:
        raise ValueError(f"Modèle inconnu : {model_name}")

    state_dict = torch.load(weights_path, map_location=DEVICE)
    # Les checkpoints peuvent contenir les poids sous ``params_ema`` ou ``params``.
    if "params_ema" in state_dict:
        state_dict = state_dict["params_ema"]
    elif "params" in state_dict:
        state_dict = state_dict["params"]

    model.load_state_dict(state_dict, strict=True)
    model.to(DEVICE)
    _set_inference_mode(model)

    _model_cache[model_name] = model
    logger.info("Modèle {model} chargé sur {device}", model=model_name, device=DEVICE)
    return model


def _set_inference_mode(model: torch.nn.Module) -> None:
    """Bascule le modèle en mode inférence (désactive dropout/batchnorm)."""
    mode_switch = getattr(model, "eval")
    mode_switch()


def _preprocess_tile(tile: np.ndarray) -> torch.Tensor:
    """Convertit une tuile HWC uint8 en tenseur NCHW float32 [0, 1]."""
    tensor = torch.from_numpy(tile).float() / 255.0
    return tensor.permute(2, 0, 1).unsqueeze(0).to(DEVICE)


def _postprocess_tile(tensor: torch.Tensor) -> np.ndarray:
    """Convertit un tenseur NCHW float32 en array HWC uint8."""
    out = tensor.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return (out * 255.0).astype(np.uint8)


def _compute_tile_grid(
    width: int, height: int, tile_size: int, overlap: int
) -> list[tuple[int, int, int, int]]:
    """Calcule la grille de tuiles couvrant l'image."""
    step = tile_size - overlap
    tiles = []
    y = 0
    while y < height:
        x = 0
        th = min(tile_size, height - y)
        while x < width:
            tw = min(tile_size, width - x)
            tiles.append((x, y, tw, th))
            if x + tile_size >= width:
                break
            x += step
        if y + tile_size >= height:
            break
        y += step
    return tiles


def _merge_tiles(
    tiles: list[tuple[tuple[int, int, int, int], np.ndarray]],
    width: int,
    height: int,
    overlap: int,
) -> np.ndarray:
    """Réassemble les tuiles avec blending linéaire aux bords."""
    canvas = np.zeros((height, width, 3), dtype=np.float64)
    weights = np.zeros((height, width), dtype=np.float64)

    for (x, y, tw, th), tile in tiles:
        has_left = x > 0
        has_top = y > 0
        has_right = x + tw < width
        has_bottom = y + th < height

        mask = np.ones((th, tw), dtype=np.float64)
        if overlap > 0:
            ramp = np.linspace(0.0, 1.0, overlap, dtype=np.float64)
            if has_left and overlap <= tw:
                mask[:, :overlap] *= ramp[np.newaxis, :]
            if has_right and overlap <= tw:
                mask[:, -overlap:] *= ramp[np.newaxis, ::-1]
            if has_top and overlap <= th:
                mask[:overlap, :] *= ramp[:, np.newaxis]
            if has_bottom and overlap <= th:
                mask[-overlap:, :] *= ramp[::-1, np.newaxis]

        ah, aw = tile.shape[:2]
        mask = mask[:ah, :aw]
        region = (slice(y, y + ah), slice(x, x + aw))
        canvas[region] += tile.astype(np.float64) * mask[:, :, np.newaxis]
        weights[region] += mask

    weights = np.maximum(weights, 1e-8)
    canvas /= weights[:, :, np.newaxis]
    return canvas.clip(0, 255).astype(np.uint8)


def run_inference(
    image: Image.Image,
    model_name: str,
    scale_factor: int,
) -> Image.Image:
    """Exécute l'inférence complète avec découpage en tuiles.

    Args:
        image: Image PIL en mode RGB.
        model_name: Nom du modèle à utiliser.
        scale_factor: Facteur de multiplication des dimensions.

    Returns:
        Image PIL upscalée.
    """
    model = load_model(model_name)

    img_array = np.array(image, dtype=np.uint8)
    h, w = img_array.shape[:2]

    grid = _compute_tile_grid(w, h, TILE_SIZE, TILE_OVERLAP)
    logger.info("Inférence — {n} tuiles pour {w}x{h}", n=len(grid), w=w, h=h)

    processed: list[tuple[tuple[int, int, int, int], np.ndarray]] = []

    with torch.no_grad():
        for tx, ty, tw, th in grid:
            tile_np = img_array[ty : ty + th, tx : tx + tw]
            tile_tensor = _preprocess_tile(tile_np)
            output_tensor = model(tile_tensor)
            output_np = _postprocess_tile(output_tensor)

            processed.append(
                (
                    (
                        tx * scale_factor,
                        ty * scale_factor,
                        tw * scale_factor,
                        th * scale_factor,
                    ),
                    output_np,
                ),
            )

    merged = _merge_tiles(
        processed,
        width=w * scale_factor,
        height=h * scale_factor,
        overlap=TILE_OVERLAP * scale_factor,
    )

    return Image.fromarray(merged, mode="RGB")


def handler(event: dict[str, Any]) -> dict[str, Any]:
    """Point d'entrée RunPod Serverless.

    Décode l'image base64, exécute l'inférence, ré-encode le résultat
    en base64 et le retourne dans le format attendu par RunPodBackend.

    Args:
        event: Payload RunPod avec la clé ``input``.

    Returns:
        Dictionnaire JSON-sérialisable avec l'image upscalée ou l'erreur.
    """
    try:
        inputs = event.get("input", {})
        image_b64 = inputs.get("image")
        if not image_b64:
            return {"error": "Champ 'image' manquant dans l'input"}

        scale_factor = int(inputs.get("scale_factor", 4))
        model_name = inputs.get("model_name", DEFAULT_MODEL)
        output_format = inputs.get("output_format", "png").lower()

        if scale_factor not in (2, 4):
            return {"error": f"scale_factor invalide : {scale_factor}"}
        if output_format not in ("png", "jpeg", "webp"):
            return {"error": f"output_format invalide : {output_format}"}

        try:
            image_bytes = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "RGB":
                image = image.convert("RGB")
        except Exception as exc:
            return {"error": f"Image source invalide : {exc}"}

        logger.info(
            "Job reçu — {w}x{h} modèle={model} facteur=x{sf}",
            w=image.width,
            h=image.height,
            model=model_name,
            sf=scale_factor,
        )

        result_image = run_inference(image, model_name, scale_factor)

        buffer = io.BytesIO()
        save_kwargs: dict[str, Any] = {}
        if output_format == "jpeg":
            save_kwargs["quality"] = 95
        elif output_format == "webp":
            save_kwargs["quality"] = 95
            save_kwargs["method"] = 6

        result_image.save(buffer, format=output_format.upper(), **save_kwargs)
        output_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        logger.info(
            "Job terminé — sortie {w}x{h} ({size} Ko)",
            w=result_image.width,
            h=result_image.height,
            size=len(buffer.getvalue()) // 1024,
        )

        return {
            "image": output_b64,
            "width": result_image.width,
            "height": result_image.height,
            "model": model_name,
            "scale_factor": scale_factor,
        }

    except Exception as exc:
        logger.exception("Erreur inattendue dans le handler")
        return {"error": f"Erreur interne : {exc}"}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
