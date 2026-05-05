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
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import runpod
import torch
from botocore.config import Config as BotoConfig
from loguru import logger
from PIL import Image

# cuDNN benchmark : teste plusieurs kernels au premier forward pour
# choisir le plus rapide. Payé une fois lors du warm-up, rentabilisé
# sur toutes les tuiles suivantes qui partagent la même shape 512x512.
torch.backends.cudnn.benchmark = True

# Configuration depuis les variables d'environnement.
# ``TILE_SIZE`` et ``TILE_OVERLAP`` doivent être des multiples de 16 (window_size
# DRCT/HAT) pour que le padding d'image produise des tuiles compatibles avec
# ``window_partition``. Les valeurs 512/32 respectent cet invariant.
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "drct-l")
TILE_SIZE = int(os.environ.get("TILE_SIZE", "512"))
TILE_OVERLAP = int(os.environ.get("TILE_OVERLAP", "32"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Stockage du résultat : ``inline`` = base64 dans le payload (limité à
# ~20 MB par RunPod), ``s3`` = upload sur un bucket S3-compatible et
# retour de l'URL (aucune limite de taille).
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "inline").lower()
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_REGION = os.environ.get("S3_REGION", "auto")

# Cache des modèles chargés (pour éviter de recharger entre les jobs).
# Clé = "{model_name}_x{scale_factor}" pour distinguer les variantes : les
# poids DRCT-L x2 et DRCT-L x4 ne sont pas interchangeables (tête
# pixelshuffle différente : 3*sf² canaux de sortie). Le worker peut servir
# les 4 combinaisons (drct-l_x2, drct-l_x4, hat-l_x2, hat-l_x4) dans le
# même process, chargées à la demande.
_model_cache: dict[str, torch.nn.Module] = {}

# Client S3 initialisé au premier usage (évite le coût au cold-start si
# l'endpoint est en mode inline).
_s3_client: Any = None


def _get_s3_client() -> Any:
    """Retourne un client boto3 S3 initialisé à la demande.

    Utilise ``virtual-host`` addressing style pour compatibilité R2.

    Raises:
        RuntimeError: Si la config S3 est incomplète.
    """
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    if not (S3_ENDPOINT_URL and S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY):
        raise RuntimeError(
            "STORAGE_BACKEND=s3 mais config S3_* incomplète "
            "(ENDPOINT_URL, BUCKET, ACCESS_KEY, SECRET_KEY requis)"
        )

    _s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )
    return _s3_client


def _resolve_weights_path(model_name: str, scale_factor: int) -> Path:
    """Localise le fichier de poids pour le couple (modèle, scale).

    Cherche en priorité ``{model_name}_x{scale_factor}.pth`` (convention
    explicite). Accepte aussi ``{model_name}.pth`` en fallback **uniquement
    pour scale_factor=4**, pour rester compatible avec les images worker
    historiques qui utilisaient le nom non-suffixé pour le x4.

    Args:
        model_name: Identifiant du modèle (``drct-l``, ``hat-l``).
        scale_factor: Facteur d'upscaling (2 ou 4).

    Returns:
        Chemin vers le fichier de poids existant.

    Raises:
        FileNotFoundError: Aucune des conventions de nom ne résout un fichier.
    """
    versioned = MODEL_DIR / f"{model_name}_x{scale_factor}.pth"
    if versioned.exists():
        return versioned

    if scale_factor == 4:
        legacy = MODEL_DIR / f"{model_name}.pth"
        if legacy.exists():
            logger.warning(
                "Utilisation du nom legacy {name} — à renommer en {versioned} "
                "pour clarté (le x2 exige déjà le nommage suffixé).",
                name=legacy.name,
                versioned=versioned.name,
            )
            return legacy

    raise FileNotFoundError(
        f"Poids introuvables pour {model_name} x{scale_factor}. Attendu : {versioned}"
    )


def load_model(model_name: str, scale_factor: int) -> torch.nn.Module:
    """Charge un modèle PyTorch depuis le disque avec cache en mémoire.

    Les poids sont cherchés dans ``MODEL_DIR/{model_name}_x{scale_factor}.pth``.
    Le code d'architecture du modèle doit être disponible (DRCT, HAT).

    Args:
        model_name: Identifiant du modèle (``drct-l``, ``hat-l``).
        scale_factor: Facteur d'upscaling natif (2 ou 4). Le modèle est
            construit avec ``upscale=scale_factor``, donc les poids doivent
            correspondre — on ne peut pas charger un checkpoint x4 dans
            une architecture x2 (tête pixelshuffle de taille différente).

    Returns:
        Modèle PyTorch en mode inférence, placé sur le bon device.

    Raises:
        FileNotFoundError: Si le fichier de poids n'existe pas.
        ValueError: Si le modèle ou le scale_factor n'est pas reconnu.
    """
    if scale_factor not in (2, 4):
        raise ValueError(f"scale_factor {scale_factor} non supporté (2 ou 4 uniquement)")

    cache_key = f"{model_name}_x{scale_factor}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    weights_path = _resolve_weights_path(model_name, scale_factor)

    if model_name == "drct-l":
        from drct.archs.DRCT_arch import DRCT

        # DRCT-L : 12 RSTB blocks (vs 6 pour DRCT de base). ``upscale`` est
        # l'unique paramètre qui varie entre les variantes x2 et x4 — la
        # tête pixelshuffle en sortie dépend directement de ce facteur
        # (``3 * upscale²`` canaux).
        model = DRCT(
            upscale=scale_factor,
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

        # HAT-L : 12 RHAG blocks (vs 6 pour HAT de base). Idem DRCT,
        # ``upscale`` impacte uniquement la tête pixelshuffle de sortie.
        model = HAT(
            upscale=scale_factor,
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

    logger.info(
        "Modèle {model} x{sf} chargé sur {device} depuis {path}",
        model=model_name,
        sf=scale_factor,
        device=DEVICE,
        path=weights_path.name,
    )

    # Warm-up cuDNN : force la compilation JIT des kernels avec la shape
    # exacte des tuiles réelles (TILE_SIZE x TILE_SIZE). Sans ça, la
    # première tuile d'un vrai job paye 3-10 min de JIT compilation
    # invisible. Refait pour chaque (modèle, scale) chargé — les kernels
    # diffèrent suffisamment entre x2 et x4 pour justifier un warmup dédié.
    if DEVICE == "cuda":
        logger.info("Warm-up cuDNN en cours (JIT compilation première tuile)...")
        t0 = time.time()
        with torch.no_grad():
            dummy = torch.randn(1, 3, TILE_SIZE, TILE_SIZE, device=DEVICE)
            _ = model(dummy)
            torch.cuda.synchronize()
        logger.info("Warm-up cuDNN terminé en {elapsed:.1f}s", elapsed=time.time() - t0)

    _model_cache[cache_key] = model
    return model


def _set_inference_mode(model: torch.nn.Module) -> None:
    """Bascule le modèle en mode inférence (désactive dropout/batchnorm)."""
    mode_switch = model.eval
    mode_switch()


def _preprocess_tile(tile: np.ndarray) -> torch.Tensor:
    """Convertit une tuile HWC uint8 en tenseur NCHW float32 [0, 1]."""
    tensor = torch.from_numpy(tile).float() / 255.0
    return tensor.permute(2, 0, 1).unsqueeze(0).to(DEVICE)


def _pad_image_to_tile_grid(
    img: np.ndarray, tile_size: int, overlap: int
) -> tuple[np.ndarray, int, int]:
    """Pad l'image pour que la grille de tuiles produise uniquement des tuiles
    pleines de taille ``tile_size x tile_size``.

    Sans ce padding, ``_compute_tile_grid`` génère des tuiles tronquées sur les
    bords droit et bas (ex. 120x80 pour une image 3000x2000), dimensions qui
    ne sont pas divisibles par le ``window_size=16`` de DRCT/HAT et cassent
    ``window_partition`` avec un shape mismatch.

    Padder l'image entière une seule fois est préférable à padder chaque tuile
    individuellement : les tuiles internes conservent un voisinage 100 % réel,
    seul le bord extrême bas-droit reçoit le padding reflet — exactement
    comme si l'image avait été un peu plus grande au départ.

    Args:
        img: Image HWC uint8.
        tile_size: Taille cible des tuiles (multiple de 16).
        overlap: Chevauchement entre tuiles consécutives (multiple de 16).

    Returns:
        Tuple ``(image_paddée, original_h, original_w)``. L'appelant crope la
        sortie upscalée à ``original_h * scale, original_w * scale``.
    """
    h, w = img.shape[:2]
    step = tile_size - overlap

    def _target(size: int) -> int:
        if size <= tile_size:
            return tile_size
        # Plus petite valeur ≥ ``size`` de la forme ``k * step + tile_size``,
        # pour que la grille de tuiles couvre exactement sans tuile tronquée.
        return ((size - tile_size + step - 1) // step) * step + tile_size

    target_h = _target(h)
    target_w = _target(w)
    pad_h = target_h - h
    pad_w = target_w - w
    if pad_h or pad_w:
        img = np.pad(img, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
    return img, h, w


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
    model = load_model(model_name, scale_factor)

    img_array = np.array(image, dtype=np.uint8)
    orig_h, orig_w = img_array.shape[:2]

    # Pad l'image pour que toutes les tuiles fassent TILE_SIZE x TILE_SIZE
    # (multiples de 16, donc compatibles avec window_partition).
    img_padded, _, _ = _pad_image_to_tile_grid(img_array, TILE_SIZE, TILE_OVERLAP)
    padded_h, padded_w = img_padded.shape[:2]

    grid = _compute_tile_grid(padded_w, padded_h, TILE_SIZE, TILE_OVERLAP)
    logger.info(
        "Inférence — {n} tuiles pour {w}x{h} (paddé {pw}x{ph})",
        n=len(grid),
        w=orig_w,
        h=orig_h,
        pw=padded_w,
        ph=padded_h,
    )

    processed: list[tuple[tuple[int, int, int, int], np.ndarray]] = []

    inference_start = time.time()
    with torch.no_grad():
        for idx, (tx, ty, tw, th) in enumerate(grid, start=1):
            tile_np = img_padded[ty : ty + th, tx : tx + tw]
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

            # Log toutes les 5 tuiles + la dernière, pour voir le progrès
            # sans saturer les logs (35 tuiles = 7 lignes typiquement).
            if idx % 5 == 0 or idx == len(grid):
                elapsed = time.time() - inference_start
                per_tile = elapsed / idx
                remaining = per_tile * (len(grid) - idx)
                logger.info(
                    "Tuiles {done}/{total} — {elapsed:.1f}s ({per:.1f}s/tuile, ETA {eta:.0f}s)",
                    done=idx,
                    total=len(grid),
                    elapsed=elapsed,
                    per=per_tile,
                    eta=remaining,
                )

    merged = _merge_tiles(
        processed,
        width=padded_w * scale_factor,
        height=padded_h * scale_factor,
        overlap=TILE_OVERLAP * scale_factor,
    )

    # Crop final aux dimensions d'origine (x scale_factor) : retire le padding
    # ajouté avant inférence. Les pixels réels n'ont jamais été altérés.
    merged = merged[: orig_h * scale_factor, : orig_w * scale_factor]

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

        # Warm-up ping : permet de démarrer le container (charger torch,
        # le modèle en VRAM) sans lancer d'inférence. Utile pour éviter
        # les cold-starts perçus par l'utilisateur final — cf.
        # stratégie de pré-warm au lancement du frontend.
        if inputs.get("ping"):
            # On pré-charge le modèle par défaut pour que le prochain vrai
            # job n'ait pas à le faire (gain ~2-3s d'init model). Le
            # ``scale_factor`` du ping détermine lequel des 2 poids
            # (x2 ou x4) est chargé — utile pour pré-warmer la bonne
            # variante avant un batch.
            ping_scale = int(inputs.get("scale_factor", 4))
            load_model(inputs.get("model_name", DEFAULT_MODEL), ping_scale)
            logger.info("Warm-up ping reçu — worker chaud et modèle chargé")
            return {"status": "ready"}

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
            "Job reçu — {w}x{h} modèle={model} facteur=x{sf} storage={storage}",
            w=image.width,
            h=image.height,
            model=model_name,
            sf=scale_factor,
            storage=STORAGE_BACKEND,
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
        output_bytes = buffer.getvalue()
        output_size_kb = len(output_bytes) // 1024

        logger.info(
            "Inférence terminée — sortie {w}x{h} ({size} Ko) — upload via {storage}",
            w=result_image.width,
            h=result_image.height,
            size=output_size_kb,
            storage=STORAGE_BACKEND,
        )

        result: dict[str, Any] = {
            "width": result_image.width,
            "height": result_image.height,
            "model": model_name,
            "scale_factor": scale_factor,
            "size_kb": output_size_kb,
        }

        if STORAGE_BACKEND == "s3":
            # Upload sur bucket S3-compatible. L'URL ``s3://bucket/key`` est
            # retournée dans l'output — le backend la téléchargera ensuite.
            key = f"outputs/{uuid.uuid4()}.{output_format}"
            content_type = f"image/{output_format if output_format != 'jpeg' else 'jpeg'}"
            _get_s3_client().put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=output_bytes,
                ContentType=content_type,
            )
            result["output_url"] = f"s3://{S3_BUCKET}/{key}"
            logger.info("Output uploadé sur s3://{bucket}/{key}", bucket=S3_BUCKET, key=key)
        else:
            # Mode inline historique : base64 dans le payload (limité à ~20 MB
            # par l'API /status de RunPod — adapté aux petits tests uniquement).
            result["image"] = base64.b64encode(output_bytes).decode("ascii")

        return result

    except Exception as exc:
        logger.exception("Erreur inattendue dans le handler")
        return {"error": f"Erreur interne : {exc}"}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
