"""Routage GPU — sélection du backend d'inférence selon les dimensions.

Détermine automatiquement si le traitement doit être effectué en local
(Core ML, Apple Silicon) ou dans le cloud (RunPod Serverless) en
fonction du nombre de mégapixels de l'image source.

Seuils de routage :
- ≤ 5 MP  →  Core ML local (gratuit, ~1-5s)
- > 5 MP  →  RunPod Serverless (payant, ~6-30s selon GPU)
"""

from loguru import logger

from app.core.gpu.interface import GPUBackend

# Seuil en mégapixels au-delà duquel le traitement est envoyé au cloud.
LOCAL_MAX_MEGAPIXELS: float = 5.0


def compute_megapixels(width: int, height: int) -> float:
    """Calcule le nombre de mégapixels d'une image.

    Args:
        width: Largeur en pixels.
        height: Hauteur en pixels.

    Returns:
        Nombre de mégapixels (ex: 12.0 pour une image 4000x3000).
    """
    return (width * height) / 1_000_000


def select_gpu_backend(
    width: int,
    height: int,
    *,
    local_backend: GPUBackend | None,
    cloud_backend: GPUBackend | None,
    prefer_local: bool | None = None,
) -> GPUBackend:
    """Sélectionne le backend GPU approprié selon les dimensions et la
    préférence utilisateur.

    Logique de routage :

    1. Si ``prefer_local=False`` (le frontend a détecté des ressources
       insuffisantes sur la machine de l'utilisateur) → cloud forcé, quel
       que soit le nombre de mégapixels.
    2. Sinon, routage classique par taille :
       - Image ≤ 5 MP : local si dispo, sinon cloud.
       - Image > 5 MP : cloud si dispo, sinon local (dégradé).

    ``prefer_local=None`` conserve le comportement legacy (routage par
    taille seule) pour la rétro-compatibilité.

    Args:
        width: Largeur de l'image en pixels.
        height: Hauteur de l'image en pixels.
        local_backend: Backend GPU local (Core ML), ``None`` si non configuré.
        cloud_backend: Backend GPU cloud (RunPod), ``None`` si non configuré.
        prefer_local: Préférence utilisateur calculée par le frontend
            (cf. ``canRunLocalStrict()``). ``False`` force le cloud même
            pour les petites images.

    Returns:
        Backend GPU sélectionné.

    Raises:
        RuntimeError: Si aucun backend GPU n'est disponible.
    """
    mp = compute_megapixels(width, height)

    if local_backend is None and cloud_backend is None:
        raise RuntimeError("Aucun backend GPU disponible — vérifier la configuration")

    # Préférence utilisateur explicite : cloud forcé malgré petite taille.
    if prefer_local is False:
        if cloud_backend is not None:
            logger.info(
                "Routage GPU → cloud (forcé par prefer_local=False) — {mp:.1f} MP",
                mp=mp,
            )
            return cloud_backend
        logger.warning(
            "prefer_local=False mais backend cloud indisponible, fallback local",
        )
        return local_backend  # type: ignore[return-value]

    if mp <= LOCAL_MAX_MEGAPIXELS:
        if local_backend is not None:
            logger.info(
                "Routage GPU → local (Core ML) — {mp:.1f} MP ≤ {seuil} MP",
                mp=mp,
                seuil=LOCAL_MAX_MEGAPIXELS,
            )
            return local_backend

        # Fallback vers le cloud si le backend local n'est pas disponible.
        logger.warning(
            "Backend local indisponible, fallback cloud pour {mp:.1f} MP",
            mp=mp,
        )
        return cloud_backend  # type: ignore[return-value]

    # Image > seuil → cloud.
    if cloud_backend is not None:
        logger.info(
            "Routage GPU → cloud (RunPod) — {mp:.1f} MP > {seuil} MP",
            mp=mp,
            seuil=LOCAL_MAX_MEGAPIXELS,
        )
        return cloud_backend

    # Fallback vers le local si le cloud n'est pas disponible.
    logger.warning(
        "Backend cloud indisponible, fallback local pour {mp:.1f} MP — "
        "traitement plus long attendu",
        mp=mp,
    )
    return local_backend  # type: ignore[return-value]
