"""GEGM Upscaler — Point d'entrée de l'application FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

# Enregistrement des modèles ORM pour que SQLAlchemy connaisse le schéma complet.
import app.jobs.models
import app.users.models
from app.core.celery import celery_app  # noqa: F401 — accessible via app.main.celery_app
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.core.redis import close_redis_pool
from app.jobs.router import router as jobs_router
from app.uploads.router import router as uploads_router

# ── Sentry — alertes d'erreurs avec stack trace ────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.2 if settings.is_development else 0.05,
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Cycle de vie de l'application : hooks de démarrage et d'arrêt."""
    setup_logging()
    logger.info(
        "Starting GEGM Upscaler API — env={env} storage={storage} auth={auth}",
        env=settings.APP_ENV,
        storage=settings.STORAGE_BACKEND,
        auth=settings.AUTH_BACKEND,
    )
    yield
    await close_redis_pool()
    await engine.dispose()
    logger.info("Shutting down GEGM Upscaler API")


app = FastAPI(
    title="GEGM Upscaler",
    description="API interne d'upscaling d'images par IA",
    version="0.1.0",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",  # Tauri dev
        "http://localhost:5173",  # Vite dev
        "tauri://localhost",  # Tauri production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus — métriques HTTP sur /metrics ───────────────────
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/api/health", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics")


app.include_router(uploads_router)
app.include_router(jobs_router)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Endpoint de health check pour les load balancers et le monitoring."""
    return {"status": "healthy", "version": "0.1.0"}
