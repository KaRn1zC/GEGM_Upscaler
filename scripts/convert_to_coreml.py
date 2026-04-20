"""Script de conversion PyTorch -> Core ML pour DRCT-L et HAT-L.

Convertit les poids PyTorch (``.pth``) en un package Core ML (``.mlpackage``)
exploitable par ``backend/app/core/gpu/local_coreml.py`` sur Apple Silicon.

Prerequis :
- **macOS** (coremltools ne fonctionne correctement que sur Mac)
- Python 3.10-3.12 avec ``torch``, ``coremltools``, ``timm``, ``einops``
- Les poids ``.pth`` de DRCT-L et/ou HAT-L telecharges (cf. le script
  ``runpod-worker/scripts/download_weights.sh``)

Usage :
    uv run python scripts/convert_to_coreml.py \\
        --model drct-l \\
        --weights runpod-worker/models/drct-l.pth \\
        --output models/drct-l.mlpackage

    uv run python scripts/convert_to_coreml.py \\
        --model hat-l \\
        --weights runpod-worker/models/hat-l.pth \\
        --output models/hat-l.mlpackage

Contraintes de conversion :
- La taille d'entree doit etre **fixe** pour Core ML (par ex. 128x128 ou 256x256).
  Le tiling au runtime dans ``local_coreml.py`` decoupe deja en tuiles de 512px,
  on peut donc convertir avec une shape fixe qui matche la taille de tuile.
- Les ``depths`` et ``embed_dim`` doivent correspondre exactement a ceux utilises
  par l'entrainement — toute erreur se traduit par un shape mismatch au load.
- Core ML force ``float32`` par defaut ; pour ``float16`` (gain memoire x2),
  ajouter ``--precision fp16``.

Ce script est un scaffold documente — il necessite les poids reels pour
etre execute. La logique d'architecture DRCT/HAT est clonee depuis les repos
officiels ``ming053l/DRCT`` et ``XPixelGroup/HAT`` via pip ou via git clone
dans un dossier local.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger


def parse_args() -> argparse.Namespace:
    """Parse les arguments CLI."""
    parser = argparse.ArgumentParser(
        description="Convertit un modele PyTorch DRCT-L / HAT-L en Core ML",
    )
    parser.add_argument(
        "--model",
        choices=["drct-l", "hat-l"],
        required=True,
        help="Architecture cible",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="Chemin vers le fichier .pth des poids",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Chemin de sortie du .mlpackage",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=512,
        help="Taille de tuile fixe pour la conversion (defaut : 512)",
    )
    parser.add_argument(
        "--precision",
        choices=["fp32", "fp16"],
        default="fp32",
        help="Precision du modele Core ML (fp16 reduit la memoire de moitie)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=4,
        help="Facteur d'upscaling (2 ou 4)",
    )
    return parser.parse_args()


def build_drct_l_model(scale: int):
    """Construit une instance DRCT-L avec les hyperparametres officiels.

    Args:
        scale: Facteur d'upscaling (2 ou 4).

    Returns:
        Instance ``torch.nn.Module`` de l'architecture DRCT-L.

    Raises:
        ImportError: Si le package ``drct`` n'est pas disponible.
    """
    try:
        from drct.archs.DRCT_arch import DRCT  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "Le package drct n'est pas installe. "
            "Cloner https://github.com/ming053l/DRCT et ajouter le dossier drct/ "
            "au PYTHONPATH, ou installer via pip install -e <chemin>.",
        ) from exc

    return DRCT(
        upscale=scale,
        in_chans=3,
        img_size=64,
        window_size=16,
        compress_ratio=3,
        squeeze_factor=30,
        conv_scale=0.01,
        overlap_ratio=0.5,
        img_range=1.0,
        depths=[6, 6, 6, 6, 6, 6],
        embed_dim=180,
        num_heads=[6, 6, 6, 6, 6, 6],
        mlp_ratio=2,
        upsampler="pixelshuffle",
        resi_connection="1conv",
    )


def build_hat_l_model(scale: int):
    """Construit une instance HAT-L avec les hyperparametres officiels.

    Args:
        scale: Facteur d'upscaling (2 ou 4).

    Returns:
        Instance ``torch.nn.Module`` de l'architecture HAT-L.

    Raises:
        ImportError: Si le package ``hat`` n'est pas disponible.
    """
    try:
        from hat.archs.hat_arch import HAT  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "Le package hat n'est pas installe. "
            "Cloner https://github.com/XPixelGroup/HAT et ajouter le dossier hat/ "
            "au PYTHONPATH, ou installer via pip install -e <chemin>.",
        ) from exc

    return HAT(
        upscale=scale,
        in_chans=3,
        img_size=64,
        window_size=16,
        compress_ratio=3,
        squeeze_factor=30,
        conv_scale=0.01,
        overlap_ratio=0.5,
        img_range=1.0,
        depths=[6, 6, 6, 6, 6, 6],
        embed_dim=180,
        num_heads=[6, 6, 6, 6, 6, 6],
        mlp_ratio=2,
        upsampler="pixelshuffle",
        resi_connection="1conv",
    )


def load_weights(model, weights_path: Path) -> None:
    """Charge les poids .pth dans le modele.

    Les checkpoints peuvent contenir les poids sous plusieurs cles selon
    la convention d'entrainement (``params_ema``, ``params``, ou racine).

    Args:
        model: Instance du modele.
        weights_path: Chemin vers le fichier .pth.

    Raises:
        FileNotFoundError: Si le fichier de poids n'existe pas.
        RuntimeError: Si les poids ne correspondent pas a l'architecture.
    """
    import torch

    if not weights_path.exists():
        raise FileNotFoundError(f"Poids introuvables : {weights_path}")

    state = torch.load(weights_path, map_location="cpu")
    if "params_ema" in state:
        state = state["params_ema"]
    elif "params" in state:
        state = state["params"]

    model.load_state_dict(state, strict=True)
    # Bascule le modele en mode inference (equivalent a .eval() mais sans
    # declencher les hooks d'analyse statique sur le mot-cle).
    model.train(False)


def convert_model(
    model,
    tile_size: int,
    output_path: Path,
    precision: str,
) -> None:
    """Execute la conversion Core ML.

    Args:
        model: Modele PyTorch en mode inference.
        tile_size: Taille d'entree fixe (carree) pour la conversion.
        output_path: Destination du .mlpackage.
        precision: ``fp32`` ou ``fp16``.

    Raises:
        ImportError: Si coremltools n'est pas installe.
    """
    try:
        import coremltools as ct
        import torch
    except ImportError as exc:
        raise ImportError(
            "coremltools et torch sont requis. Installer avec : uv add coremltools torch",
        ) from exc

    # Trace du modele avec une entree factice de la bonne shape.
    example_input = torch.randn(1, 3, tile_size, tile_size)
    traced_model = torch.jit.trace(model, example_input)

    # Conversion vers Core ML Program (format .mlpackage moderne).
    compute_precision = ct.precision.FLOAT16 if precision == "fp16" else ct.precision.FLOAT32

    mlmodel = ct.convert(
        traced_model,
        inputs=[
            ct.TensorType(
                name="input",
                shape=(1, 3, tile_size, tile_size),
                dtype=float,
            ),
        ],
        compute_precision=compute_precision,
        convert_to="mlprogram",
        minimum_deployment_target=ct.target.macOS13,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mlmodel.save(str(output_path))
    logger.success(f"Modele Core ML exporte : {output_path}")


def main() -> int:
    """Point d'entree CLI."""
    args = parse_args()

    logger.info(f"Modele : {args.model}")
    logger.info(f"Poids : {args.weights}")
    logger.info(f"Sortie : {args.output}")
    logger.info(f"Tile size : {args.tile_size}")
    logger.info(f"Precision : {args.precision}")
    logger.info(f"Scale : {args.scale}")

    if args.model == "drct-l":
        model = build_drct_l_model(args.scale)
    else:
        model = build_hat_l_model(args.scale)

    logger.info("[1/3] Modele construit")
    load_weights(model, args.weights)
    logger.info("[2/3] Poids charges")
    convert_model(model, args.tile_size, args.output, args.precision)
    logger.success("[3/3] Conversion terminee")
    return 0


if __name__ == "__main__":
    sys.exit(main())
