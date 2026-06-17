"""Fabrique du backend GPU cloud (RunPod), partagée entre le worker et l'API.

Le worker Celery (pipeline d'upscale) et l'API (pré-warm) construisent le même
backend cloud. Centralisé ici pour rester DRY et respecter le principe
d'abstraction : le métier ne référence que ``GPUBackend``, jamais
``RunPodBackend`` en dur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from app.core.config import settings

if TYPE_CHECKING:
    from app.core.gpu.interface import GPUBackend


def build_cloud_gpu_backend() -> GPUBackend | None:
    """Construit le backend RunPod depuis la config, ou ``None`` si absent.

    La config ``S3_OUTPUT_*`` est optionnelle : si présente, le backend peut
    télécharger les outputs volumineux uploadés par le handler sur le bucket ;
    sinon il retombe sur les outputs inline base64.

    Returns:
        Instance ``RunPodBackend`` si ``RUNPOD_API_KEY`` et
        ``RUNPOD_ENDPOINT_ID`` sont configurés, sinon ``None``.
    """
    api_key = settings.RUNPOD_API_KEY.get_secret_value()
    endpoint_id = settings.RUNPOD_ENDPOINT_ID

    if not api_key or not endpoint_id:
        logger.debug("Credentials RunPod absents — backend cloud désactivé")
        return None

    from app.core.gpu.runpod import RunPodBackend

    return RunPodBackend(
        api_key=api_key,
        endpoint_id=endpoint_id,
        s3_endpoint_url=settings.S3_OUTPUT_ENDPOINT_URL,
        s3_bucket=settings.S3_OUTPUT_BUCKET,
        s3_access_key=settings.S3_OUTPUT_ACCESS_KEY.get_secret_value(),
        s3_secret_key=settings.S3_OUTPUT_SECRET_KEY.get_secret_value(),
        s3_region=settings.S3_OUTPUT_REGION,
    )
