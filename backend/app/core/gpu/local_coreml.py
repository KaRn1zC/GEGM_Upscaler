"""Backend GPU local via Core ML sur Apple Silicon.

Charge un modèle de super-résolution au format ``.mlpackage`` et
exécute l'inférence directement sur le Neural Engine / GPU Apple.
Destiné aux images ≤ 5 MP pour un traitement quasi instantané.

Le modèle est chargé paresseusement au premier appel et gardé en
mémoire pour les appels suivants. Les résultats sont stockés dans
un dictionnaire interne indexé par job ID.
"""

from __future__ import annotations

import asyncio
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from app.core.gpu.interface import GPUBackend, GPUJobResult, GPUJobStatus, UpscaleParams
from app.upscaling.preprocessing import (
    array_to_image,
    decode_image,
    encode_image,
    image_to_array,
)
from app.upscaling.tiling import merge_tiles, split_into_tiles

# Taille des tuiles et chevauchement (pixels) — adaptés à DRCT-L.
_TILE_SIZE: int = 512
_TILE_OVERLAP: int = 32


@lru_cache(maxsize=2)
def _load_model(model_path: str) -> Any:
    """Charge un modèle Core ML depuis le disque (avec cache).

    Le cache LRU évite de recharger le modèle à chaque inférence.
    ``maxsize=2`` permet de garder le modèle principal et le fallback.

    Args:
        model_path: Chemin vers le fichier ``.mlpackage`` ou ``.mlmodelc``.

    Returns:
        Instance ``coremltools.models.MLModel`` prête pour la prédiction.

    Raises:
        FileNotFoundError: Si le fichier modèle n'existe pas.
        ImportError: Si ``coremltools`` n'est pas installé.
    """
    try:
        import coremltools as ct
    except ImportError as exc:
        raise ImportError(
            "coremltools est requis pour l'inférence Core ML. Installer avec : uv add coremltools"
        ) from exc

    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Modèle introuvable : {model_path}")

    logger.info("Chargement du modèle Core ML : {path}", path=model_path)
    model = ct.models.MLModel(str(path))
    logger.info("Modèle Core ML chargé avec succès")
    return model


def _infer_tile(model: Any, tile: NDArray[np.float32]) -> NDArray[np.float32]:
    """Exécute l'inférence Core ML sur une tuile unique.

    Le modèle DRCT-L attend un tenseur ``(1, 3, H, W)`` en float32 et
    retourne un tenseur ``(1, 3, H*scale, W*scale)``.

    Args:
        model: Modèle Core ML chargé.
        tile: Tuile ``(H, W, 3)`` en float32 normalisé [0, 1].

    Returns:
        Tuile upscalée ``(H*scale, W*scale, 3)`` en float32.
    """
    # HWC → CHW → NCHW (format attendu par le modèle).
    tensor = np.transpose(tile, (2, 0, 1))[np.newaxis, :]

    # Prédiction Core ML.
    prediction = model.predict({"input": tensor})

    # Extraire le tenseur de sortie (clé variable selon la conversion).
    output_key = next(iter(prediction))
    output = prediction[output_key]

    # NCHW → CHW → HWC.
    if output.ndim == 4:
        output = output[0]
    return np.transpose(output, (1, 2, 0)).astype(np.float32)


class CoreMLBackend(GPUBackend):
    """Inférence locale sur Apple Silicon via Core ML.

    Les jobs sont exécutés de manière synchrone dans un thread pool
    pour ne pas bloquer l'event loop async. Les résultats sont stockés
    en mémoire et récupérés via ``get_job_status``.

    Attributes:
        _model_path: Chemin vers le modèle ``.mlpackage``.
        _results: Cache des résultats indexés par job ID.
    """

    def __init__(self, model_path: str) -> None:
        """Initialise le backend Core ML.

        Args:
            model_path: Chemin vers le fichier modèle Core ML.
        """
        self._model_path = model_path
        self._results: dict[str, GPUJobResult] = {}
        self._output_data: dict[str, bytes] = {}

    async def submit_job(self, image_data: bytes, params: UpscaleParams) -> str:
        """Soumet une image pour upscaling via Core ML.

        L'inférence est exécutée dans un thread pool (via
        ``asyncio.to_thread``) pour ne pas bloquer l'event loop.
        Le résultat est stocké en mémoire et accessible via
        ``get_job_status``.

        Args:
            image_data: Bytes bruts de l'image source.
            params: Paramètres d'upscaling.

        Returns:
            Identifiant unique du job local.
        """
        job_id = f"coreml-{uuid.uuid4().hex[:12]}"

        logger.info(
            "Job Core ML soumis — id={job_id} model={model}",
            job_id=job_id,
            model=params.model_name,
        )

        self._results[job_id] = GPUJobResult(
            status=GPUJobStatus.PROCESSING,
            progress=0.1,
        )

        try:
            output_bytes = await asyncio.to_thread(self._run_inference, image_data, params)

            self._results[job_id] = GPUJobResult(
                status=GPUJobStatus.COMPLETED,
                progress=1.0,
                output_key=job_id,
            )

            # Stocker les bytes de sortie pour récupération ultérieure.
            self._output_data[job_id] = output_bytes

            logger.info("Job Core ML terminé — id={job_id}", job_id=job_id)

        except Exception as exc:
            self._results[job_id] = GPUJobResult(
                status=GPUJobStatus.FAILED,
                error=str(exc),
            )
            logger.error(
                "Job Core ML échoué — id={job_id} erreur={err}",
                job_id=job_id,
                err=str(exc),
            )

        return job_id

    async def get_job_status(self, job_id: str) -> GPUJobResult:
        """Retourne le statut d'un job Core ML local.

        Args:
            job_id: Identifiant retourné par ``submit_job``.

        Returns:
            État courant du job.
        """
        return self._results.get(
            job_id,
            GPUJobResult(status=GPUJobStatus.FAILED, error="Job inconnu"),
        )

    def get_output_data(self, job_id: str) -> bytes | None:
        """Récupère les bytes de l'image de sortie d'un job terminé.

        Args:
            job_id: Identifiant du job.

        Returns:
            Bytes de l'image upscalée, ou ``None`` si non disponible.
        """
        return self._output_data.get(job_id)

    def _run_inference(self, image_data: bytes, params: UpscaleParams) -> bytes:
        """Exécute le pipeline complet d'inférence (synchrone).

        Décode → tile → infer → merge → encode.

        Args:
            image_data: Bytes bruts de l'image source.
            params: Paramètres d'upscaling.

        Returns:
            Bytes de l'image upscalée dans le format demandé.
        """
        model = _load_model(self._model_path)

        # Décodage et conversion en array.
        img = decode_image(image_data)
        arr = image_to_array(img)
        h, w = arr.shape[:2]

        logger.debug(
            "Inférence Core ML — {w}x{h} pixels, facteur x{s}",
            w=w,
            h=h,
            s=params.scale_factor,
        )

        # Découpage en tuiles.
        uint8_arr = (arr * 255).clip(0, 255).astype(np.uint8)
        tiles = split_into_tiles(uint8_arr, _TILE_SIZE, _TILE_OVERLAP)

        # Inférence sur chaque tuile.
        processed: list[tuple[tuple[int, int, int, int], NDArray[np.uint8]]] = []
        sf = params.scale_factor

        for (tx, ty, tw, th), tile_uint8 in tiles:
            tile_float = tile_uint8.astype(np.float32) / 255.0
            output_float = _infer_tile(model, tile_float)
            output_uint8 = (output_float * 255).clip(0, 255).astype(np.uint8)

            # Les coordonnées sont mises à l'échelle pour l'espace de sortie.
            processed.append(((tx * sf, ty * sf, tw * sf, th * sf), output_uint8))

        # Réassemblage.
        result_arr = merge_tiles(
            processed,
            output_width=w * sf,
            output_height=h * sf,
            overlap=_TILE_OVERLAP * sf,
        )

        # Encodage vers le format de sortie.
        result_img = array_to_image(result_arr.astype(np.float32) / 255.0)
        return encode_image(result_img, params.output_format)
