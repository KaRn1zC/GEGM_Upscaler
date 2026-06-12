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

# Args injectés à `docker build --build-arg` pour configurer l'app au
# build-time (Vite remplace les `import.meta.env.VITE_*` par leur valeur
# dans le bundle). Defaults = mode dev → pas de redirect OIDC.
#
# Pour un build prod, passer dans le workflow CI :
#   --build-arg VITE_AUTH_MODE=oidc
#   --build-arg VITE_API_BASE=https://upscaler.gegmgroup.com/api
#   --build-arg VITE_OIDC_ISSUER=https://keycloak.gegm.internal/realms/gegm
#   --build-arg VITE_OIDC_CLIENT_ID=gegm-upscaler
ARG VITE_AUTH_MODE=dev
ARG VITE_API_BASE=
ARG VITE_OIDC_ISSUER=
ARG VITE_OIDC_CLIENT_ID=gegm-upscaler
# Sentry (optionnel) — DSN vide = pas d'init, pas d'overhead réseau.
ARG VITE_SENTRY_DSN=
ARG VITE_SENTRY_ENVIRONMENT=production
ARG VITE_APP_VERSION=

ENV VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_API_BASE=$VITE_API_BASE \
    VITE_OIDC_ISSUER=$VITE_OIDC_ISSUER \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT \
    VITE_APP_VERSION=$VITE_APP_VERSION

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
# L'upgrade absorbe les patches sécurité Debian publiés entre deux refresh
# de l'image de base (CVE gnutls/openssl bloquantes au scan Trivy sinon).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
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

# Pré-création des dossiers montés en volume (storage local + cache modèles
# Core ML). Sans ce mkdir+chown, Docker crée les volumes nommés en root:root
# au premier mount et l'app non-root (UID 1000) ne peut pas y écrire.
# En K8s, le securityContext.fsGroup=1000 du chart Helm joue le même rôle.
RUN mkdir -p /data /models \
    && chown -R app:app /data /models

USER app
EXPOSE 8000

# Par défaut : API FastAPI. Le service Celery override avec sa propre commande.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
