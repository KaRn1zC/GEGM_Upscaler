# Dockerfile multi-stage pour le backend GEGM Upscaler.
# Stage 1 (builder) : installation des dépendances via uv dans un venv.
# Stage 2 (runtime) : image minimale avec uniquement le venv et le code.

# ──────────────────────────────────────────────────────────────
# Stage 1 — Builder
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Installation de uv depuis l'image officielle (binaire statique).
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

# Dépendances système requises par Pillow et asyncpg.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Couche 1 : résolution des dépendances (cachée tant que pyproject/lock inchangés) ──
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --no-group dev

# ── Couche 2 : code applicatif ──
COPY backend/ ./backend/
COPY alembic.ini ./

# ──────────────────────────────────────────────────────────────
# Stage 2 — Runtime
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# Deps runtime seulement (pas de build-essential).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 app \
    && useradd -u 1000 -g app -m -s /bin/bash app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Copie du venv et du code depuis le builder.
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /build/backend /app/backend
COPY --from=builder --chown=app:app /build/alembic.ini /app/

USER app
EXPOSE 8000

# Par défaut : API FastAPI. Le service Celery override avec sa propre commande.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
