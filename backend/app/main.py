"""GEGM Upscaler — Point d'entrée de l'application FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging


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


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Endpoint de health check pour les load balancers et le monitoring."""
    return {"status": "healthy", "version": "0.1.0"}
