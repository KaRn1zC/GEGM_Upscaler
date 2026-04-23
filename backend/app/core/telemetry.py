"""Initialisation OpenTelemetry — traces distribuées pour l'API et les workers.

Remplace ``prometheus-fastapi-instrumentator`` (qui ne gérait que les métriques
HTTP de l'API) par une stack OpenTelemetry complète :

- **Traces** exportées au collector OTLP configuré (FastAPI → Celery → RunPod).
  Aucun trafic si ``OTEL_EXPORTER_OTLP_ENDPOINT`` est vide — init no-op.
- **Instrumentations automatiques** : FastAPI, Celery, SQLAlchemy, asyncpg,
  Redis, httpx, logging.
- **Métriques Prometheus custom** (``upscale_jobs_total``,
  ``upscale_duration_seconds``) : conservées via ``prometheus_client``, exposées
  sur ``/metrics`` côté API et via ``start_http_server`` côté worker. Les
  métriques HTTP automatiques précédemment fournies par ``prometheus-fastapi-instrumentator``
  sont remplacées par les spans OTel (``http.server.*``) exportés vers le
  collector — si la stack GEGM veut absolument du Prometheus pour ces
  séries, le collector OTel les convertit en métriques Prom via son pipeline.

L'init est idempotente : un second appel est un no-op (guard par
``_initialized``). Cela permet d'appeler ``init_telemetry`` à la fois depuis
le lifespan FastAPI et depuis ``worker_process_init`` Celery sans risquer un
double-register des instrumentations.
"""

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.core.config import settings

_initialized: bool = False


def init_telemetry(service_name: str | None = None) -> None:
    """Initialise le TracerProvider OTel global.

    Appelée au démarrage de l'API (lifespan) et de chaque worker Celery
    (signal ``worker_process_init``). Idempotente — un 2e appel n'a aucun
    effet.

    Args:
        service_name: Surcharge du nom de service pour cet appel.
            Utile pour distinguer ``gegm-upscaler-api`` et
            ``gegm-upscaler-worker`` dans les traces agrégées, même si les
            deux process lisent le même ``Settings``. Vide → utilise
            ``settings.OTEL_SERVICE_NAME``.
    """
    global _initialized
    if _initialized:
        return

    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.info("OTel désactivé (OTEL_EXPORTER_OTLP_ENDPOINT vide)")
        _initialized = True
        return

    resource = Resource.create(
        {
            "service.name": service_name or settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.APP_ENV,
        }
    )

    # Échantillonnage : ParentBased permet à une trace commencée en amont
    # (ex. requête HTTP avec header traceparent) de conserver sa décision,
    # tandis que les traces root respectent le ratio configuré.
    sampler = ParentBased(root=TraceIdRatioBased(settings.OTEL_TRACES_SAMPLER_RATIO))

    provider = TracerProvider(resource=resource, sampler=sampler)
    exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=settings.OTEL_EXPORTER_OTLP_INSECURE,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Instrumentations "transversales" — indépendantes de FastAPI/Celery
    # spécifiques (instrumentées plus tard via leurs fonctions dédiées).
    SQLAlchemyInstrumentor().instrument()
    # AsyncPG : le package n'a pas de stubs typés upstream — on ignore le
    # warning mypy plutôt que d'écrire un .pyi juste pour ce constructeur.
    AsyncPGInstrumentor().instrument()  # type: ignore[no-untyped-call]
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    # Injecte trace_id/span_id dans les LogRecord standard — utile pour
    # corréler logs Loguru et traces Tempo/Jaeger côté observabilité.
    LoggingInstrumentor().instrument(set_logging_format=True)

    logger.info(
        "OTel initialisé (service={service}, endpoint={endpoint}, sampler={ratio})",
        service=service_name or settings.OTEL_SERVICE_NAME,
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        ratio=settings.OTEL_TRACES_SAMPLER_RATIO,
    )

    _initialized = True


def instrument_fastapi(app: object) -> None:
    """Instrumente une application FastAPI spécifique.

    Séparé de ``init_telemetry`` parce que l'instrumentation FastAPI doit
    recevoir l'objet ``app`` — on ne peut pas le faire en "global".
    Idempotent par FastAPIInstrumentor (un 2e appel lève une exception
    silencieusement ignorée).

    Args:
        app: Instance FastAPI à instrumenter.
    """
    # Import local pour éviter d'importer FastAPIInstrumentor côté worker
    # Celery qui n'a pas FastAPI sur le chemin critique.
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]


def instrument_celery() -> None:
    """Instrumente Celery — worker + producer.

    À appeler une fois côté worker (dans ``worker_process_init``) et une
    fois côté API (au lifespan startup) pour que les ``delay()`` et
    ``apply_async()`` propagent le contexte trace vers les workers.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    CeleryInstrumentor().instrument()
