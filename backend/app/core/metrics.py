"""Métriques Prometheus custom exposées par l'API et les workers Celery.

Complémentent les métriques automatiques de ``prometheus-fastapi-instrumentator``
(RPS, latence HTTP, codes de statut) avec des compteurs métier ciblés sur le
pipeline d'upscaling :

- ``upscale_jobs_total{status, backend, model}`` : nombre cumulé de jobs
  traités, ventilé par statut (completed/failed), backend (local/cloud) et
  modèle (drct-l/hat-l).
- ``upscale_duration_seconds{backend, model}`` : distribution des durées
  totales d'un upscale (de la création du job jusqu'à la finalisation).

Alimentées depuis ``app.upscaling.pipeline`` (étapes save et
on_pipeline_failure). Exposées :

- Côté API : automatiquement via ``prometheus-fastapi-instrumentator`` qui
  utilise le registry par défaut (``/metrics``).
- Côté worker Celery : via ``start_metrics_server(port)`` appelé depuis
  un handler ``worker_process_init`` (cf. ``jobs.tasks``).
"""

from prometheus_client import Counter, Histogram

# Nombre total de jobs d'upscaling finalisés (succès ou échec).
# Labels :
#   - status : "completed" | "failed"
#   - backend : "local" | "cloud" | "unknown" (si échec avant routage)
#   - model : "drct-l" | "hat-l" | "unknown"
upscale_jobs_total = Counter(
    "upscale_jobs_total",
    "Nombre total de jobs d'upscaling traités.",
    labelnames=("status", "backend", "model"),
)

# Durée end-to-end d'un upscale (création du job → finalisation).
# Buckets adaptés à la plage réaliste : inférence Core ML locale (~5 s),
# RunPod warm (~5-10 min), RunPod cold start (~15 min), timeout (>15 min).
upscale_duration_seconds = Histogram(
    "upscale_duration_seconds",
    "Durée d'un upscale complet en secondes (création du job → finalisation).",
    labelnames=("backend", "model"),
    buckets=(10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0, 1800.0),
)


def start_metrics_server(port: int = 8001) -> None:
    """Démarre un serveur HTTP Prometheus sur le port indiqué.

    Utilisé par les workers Celery qui tournent dans un process séparé de
    l'API FastAPI. Le serveur expose ``/metrics`` au format Prometheus sur
    toutes les interfaces (0.0.0.0) pour que Prometheus puisse scraper via
    le nom DNS du conteneur (ex. ``worker:8001``).

    Args:
        port: Port d'écoute du serveur (8001 par défaut, pour distinguer
            de l'API sur 8000).
    """
    from prometheus_client import start_http_server

    start_http_server(port)
