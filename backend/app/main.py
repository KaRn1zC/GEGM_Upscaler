"""GEGM Upscaler — Point d'entrée de l'application FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.celery import celery_app  # noqa: F401 — accessible via app.main.celery_app
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.core.redis import close_redis_pool

# Enregistrement des modèles ORM pour que SQLAlchemy connaisse le schéma complet.
# L'alias ``as _`` évite la confusion mypy entre le package ``app`` et la
# variable ``app = FastAPI(...)`` déclarée plus bas.
from app.jobs import models as _jobs_models  # noqa: F401
from app.jobs.router import router as jobs_router
from app.uploads.router import router as uploads_router
from app.users import models as _users_models  # noqa: F401
from app.users.router import router as users_router

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
    allow_origins=settings.CORS_ORIGINS,
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
app.include_router(users_router)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Liveness probe — vérifie simplement que le process répond."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/api/health/ready")
async def readiness_check() -> dict[str, object]:
    """Readiness probe — vérifie les dépendances critiques (DB + Redis).

    Utilisée par les orchestrateurs pour décider si le pod peut recevoir
    du trafic. Retourne 200 avec le détail de chaque check, ou lève une
    HTTPException 503 si une dépendance est indisponible.

    Raises:
        HTTPException: 503 si la DB ou Redis ne répond pas.
    """
    from sqlalchemy import text

    from app.core.redis import get_redis_pool

    checks: dict[str, str] = {}

    # Check DB : requête simple SELECT 1.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health check DB failed: {err}", err=str(exc))
        checks["database"] = f"error: {exc}"

    # Check Redis : PING.
    try:
        redis = get_redis_pool()
        pong = await redis.ping()
        checks["redis"] = "ok" if pong else "error: no pong"
    except Exception as exc:
        logger.error("Health check Redis failed: {err}", err=str(exc))
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail={"status": "unhealthy", "checks": checks})

    return {"status": "ready", "checks": checks}
