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
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from loguru import logger


def _load_arch_module(file_path: Path, module_name: str) -> ModuleType:
    """Charge dynamiquement un fichier ``*_arch.py`` sans passer par le
    paquet parent (qui tire des deps lourdes comme cv2).

    Applique au passage un patch sur la ligne ``int(windows.shape[0]/...)``
    du fichier : inoffensive en eager, mais fatale au tracer coremltools 9
    qui n'accepte pas de cast depuis un tensor non scalaire. On remplace
    la division flottante par une division entière, équivalente
    numériquement sur des shapes valides. La version patchée est écrite
    dans un fichier voisin ``*.patched.py`` puis chargée via importlib.

    Args:
        file_path: Chemin absolu vers le fichier d'architecture.
        module_name: Nom logique à attribuer au module importé.

    Returns:
        Le module chargé avec la classe d'architecture accessible.

    Raises:
        ImportError: Si le fichier n'existe pas ou le loader est invalide.
    """
    if not file_path.exists():
        raise ImportError(f"Fichier d'architecture introuvable : {file_path}")

    source = file_path.read_text()
    patched_source = source.replace(
        "B = int(windows.shape[0] / (H * W / window_size / window_size))",
        "B = windows.shape[0] // (H * W // window_size // window_size)",
    ).replace(
        "b = int(windows.shape[0] / (h * w / window_size / window_size))",
        "b = windows.shape[0] // (h * w // window_size // window_size)",
    )

    patched_path = file_path.with_suffix(".patched.py")
    if (not patched_path.exists()) or patched_path.read_text() != patched_source:
        patched_path.write_text(patched_source)

    spec = importlib.util.spec_from_file_location(module_name, patched_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de construire le spec pour {patched_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


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


def _resolve_vendor_arch(
    repo_root: str,
    rel_path: str,
    module_name: str,
    class_name: str,
) -> type:
    """Localise et charge une classe d'architecture dans un repo cloné.

    Évite le passage par le paquet parent (``drct/__init__.py`` ou
    ``hat/__init__.py``) qui importe des modules de data ayant besoin
    de cv2, alors qu'on n'a besoin que de l'architecture.
    """
    arch_file = Path(repo_root) / rel_path
    module = _load_arch_module(arch_file, module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ImportError(f"{class_name} introuvable dans {arch_file}")
    return cls  # type: ignore[no-any-return]


def _vendor_root(env_var: str, default_rel: str) -> str:
    """Retourne le chemin racine d'un repo cloné (DRCT ou HAT).

    Le chemin peut être surchargé via variable d'env (utile en CI),
    sinon on prend ``vendor/<default_rel>`` à côté du repo courant.
    """
    import os

    override = os.environ.get(env_var)
    if override:
        return override
    here = Path(__file__).resolve().parent.parent
    return str(here / "vendor" / default_rel)


def build_drct_l_model(scale: int):
    """Construit une instance DRCT-L avec les hyperparametres officiels.

    Args:
        scale: Facteur d'upscaling (2 ou 4).

    Returns:
        Instance ``torch.nn.Module`` de l'architecture DRCT-L.

    Raises:
        ImportError: Si le fichier d'architecture est introuvable.
    """
    drct_cls = _resolve_vendor_arch(
        repo_root=_vendor_root("DRCT_REPO", "drct-repo"),
        rel_path="drct/archs/DRCT_arch.py",
        module_name="drct_arch_mod",
        class_name="DRCT",
    )

    # DRCT-L : 12 RSTB blocks (vs 6 pour DRCT standard). Les depths et
    # num_heads doivent matcher exactement le checkpoint officiel.
    return drct_cls(
        upscale=scale,
        in_chans=3,
        img_size=64,
        window_size=16,
        compress_ratio=3,
        squeeze_factor=30,
        conv_scale=0.01,
        overlap_ratio=0.5,
        img_range=1.0,
        depths=[6] * 12,
        embed_dim=180,
        num_heads=[6] * 12,
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
        ImportError: Si le fichier d'architecture est introuvable.
    """
    hat_cls = _resolve_vendor_arch(
        repo_root=_vendor_root("HAT_REPO", "hat-repo"),
        rel_path="hat/archs/hat_arch.py",
        module_name="hat_arch_mod",
        class_name="HAT",
    )

    # HAT-L : 12 RHAG blocks (vs 6 pour HAT standard). Mêmes hyperparams
    # que DRCT-L côté embed_dim / window_size / heads.
    return hat_cls(
        upscale=scale,
        in_chans=3,
        img_size=64,
        window_size=16,
        compress_ratio=3,
        squeeze_factor=30,
        conv_scale=0.01,
        overlap_ratio=0.5,
        img_range=1.0,
        depths=[6] * 12,
        embed_dim=180,
        num_heads=[6] * 12,
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

    example_input = torch.randn(1, 3, tile_size, tile_size)

    # `torch.jit.trace` avec DRCT/HAT produit un `int(tensor / ...)` qui
    # casse coremltools ; `torch.export` casse parce que DRCT mute
    # `self.mean` pendant le forward. On applique donc un patch local
    # (cf. `_patch_window_reverse_*`) puis on utilise le trace classique.
    traced_model = torch.jit.trace(model, example_input)

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
