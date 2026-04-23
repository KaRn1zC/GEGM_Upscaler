# Dockerfile multi-stage pour le backend GEGM Upscaler.
#
# Stage 1 (python-builder) : installation des dépendances Python via uv.
# Stage 2 (frontend-builder) : build du SPA Vite en parallèle.
# Stage 3 (runtime) : image minimale avec venv Python + dist/ frontend + code.
#
# En prod K8s, l'image unique sert à la fois l'API FastAPI et le frontend
# (FastAPI mount StaticFiles + fallback SPA sur `index.html` — cf.
# `backend/app/main.py` en bas de fichier). Un seul Deployment, une seule
# image, un seul cycle de release.

# ──────────────────────────────────────────────────────────────
# Stage 1 — Python builder
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS python-builder

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
# Stage 2 — Frontend builder (Vite)
# ──────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend

# ── Couche 1 : dépendances npm (cachée tant que package-lock inchangé) ──
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --prefer-offline

# ── Couche 2 : code + build ──
COPY frontend/ ./
# `tsc -b && vite build` → /build/frontend/dist/
RUN npm run build

# ──────────────────────────────────────────────────────────────
# Stage 3 — Runtime
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# Deps runtime seulement (pas de build-essential, pas de Node).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 app \
    && useradd -u 1000 -g app -m -s /bin/bash app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    FRONTEND_DIST=/app/frontend/dist

WORKDIR /app

# Backend Python (venv + code)
COPY --from=python-builder --chown=app:app /opt/venv /opt/venv
COPY --from=python-builder --chown=app:app /build/backend /app/backend
COPY --from=python-builder --chown=app:app /build/alembic.ini /app/

# Frontend build statique (servi par FastAPI StaticFiles)
COPY --from=frontend-builder --chown=app:app /build/frontend/dist /app/frontend/dist

USER app
EXPOSE 8000

# Par défaut : API FastAPI. Le service Celery override avec sa propre commande.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
