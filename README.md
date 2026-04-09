# GEGM Upscaler

Outil interne GEGM d'upscaling d'images par super-résolution IA.
Spécification complète et décisions d'architecture : voir [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Stack

- **Backend** : FastAPI + Celery + Redis + PostgreSQL (async SQLAlchemy + asyncpg)
- **Frontend** : React 19 + TypeScript + Vite + Tailwind CSS 4 + Zustand
- **Desktop** : Tauri 2.0 (Rust + WKWebView)
- **Modèle SR** : DRCT-L (`ming053l/DRCT`), fallback HAT-L
- **GPU** : Core ML (Apple Silicon, ≤5 MP) + RunPod Serverless (cloud, >5 MP)
- **Monitoring** : Loguru + Promtail → Loki, Prometheus → Grafana, Sentry, Flower

## Prérequis

- **Python 3.12+** (géré par [uv](https://github.com/astral-sh/uv))
- **Node.js 20+** (pour le frontend)
- **Rust 1.77+** (pour le shell Tauri)
- **Docker Desktop** (pour la stack locale)

## Installation

```bash
# Dépendances Python (backend)
uv sync

# Dépendances frontend
cd frontend && npm install && cd ..

# Copie du template d'environnement
cp .env.example .env
```

## Commandes

### Stack complète via Docker Compose

```bash
# Lancer tout : Postgres + Redis + API + Worker Celery
docker compose up -d

# Avec le monitoring : Loki + Prometheus + Grafana + Flower
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Logs en temps réel
docker compose logs -f api worker

# Arrêt
docker compose down

# Reset complet (supprime les volumes)
docker compose down -v
```

Services exposés :

| Service | URL | Credentials |
|---------|-----|-------------|
| API FastAPI | http://localhost:8000 | Bearer `dev-secret-token-change-me` |
| API Docs (Swagger) | http://localhost:8000/api/docs | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Loki | http://localhost:3100 | — |
| Flower | http://localhost:5555 | — |
| PostgreSQL | localhost:5432 | upscaler / upscaler |
| Redis | localhost:6379 | — |

### Backend en dev local (hors Docker)

```bash
# Services d'infrastructure uniquement
docker compose up -d postgres redis

# Migrations DB
cd backend && uv run alembic upgrade head

# API en mode rechargement
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Worker Celery
cd backend && uv run celery -A app.main.celery_app worker --loglevel=info

# Créer une nouvelle migration
cd backend && uv run alembic revision --autogenerate -m "description"
```

### Qualité du code (backend)

```bash
uv run ruff check backend/              # Linter
uv run ruff check --fix backend/        # Auto-fix
uv run ruff format backend/             # Formatter
uv run mypy backend/app/                # Type checking
uv run pytest                           # Tests
uv run pytest --cov=app --cov-report=html  # Tests avec couverture
```

### Frontend (Vite)

```bash
cd frontend

npm run dev          # Serveur de dev Vite (http://localhost:5173)
npm run build        # Build production dans dist/
npm run lint         # ESLint
```

### Desktop (Tauri)

```bash
cd frontend

npm run tauri:dev    # Lance l'app en mode dev (Vite + Tauri hot reload)
npm run tauri:build  # Produit le bundle macOS (.app + .dmg)
```

Le bundle final se trouve dans `frontend/src-tauri/target/release/bundle/`.

### RunPod Worker (serverless)

Voir [`runpod-worker/README.md`](./runpod-worker/README.md) pour la procédure complète de build
et de déploiement de l'image Docker vers un endpoint RunPod Serverless.

```bash
# Build de l'image Docker
docker build -t <registry>/gegm-upscaler-worker:latest runpod-worker/

# Push vers le registry
docker push <registry>/gegm-upscaler-worker:latest
```

## Architecture

Le principe fondamental du projet : **chaque couche d'infrastructure est abstraite derrière
une ABC Python**. Le code métier ne parle qu'aux interfaces ; le swap d'implémentation se
fait via `.env` sans modifier le code.

| Interface | Dev (local) | Prod |
|-----------|-------------|------|
| `StorageBackend` | Filesystem local | S3 / R2 / GCS |
| `AuthBackend` | Token statique | OIDC (JWT) |
| `SecretsBackend` | `os.environ` | Infisical / Vault |
| `GPUBackend` | Core ML local | RunPod Serverless |

Structure :

```
GEGM_Upscaler/
├── backend/               # API FastAPI + worker Celery
│   ├── app/
│   │   ├── core/         # Infrastructure (storage, auth, secrets, gpu, db, redis)
│   │   ├── jobs/         # Module métier — gestion des jobs d'upscaling
│   │   ├── uploads/      # Module métier — upload d'images
│   │   ├── upscaling/    # Pipeline SR (tiling, preprocessing, routage GPU)
│   │   └── users/        # Module métier — utilisateurs
│   ├── alembic/          # Migrations DB versionnées
│   ├── tests/            # Tests pytest (85+ tests)
│   └── Dockerfile        # Image multi-stage (builder → runtime)
│
├── frontend/              # React 19 + Vite + Tailwind 4
│   ├── src/
│   │   ├── components/   # DropZone, JobCard, CompareSlider
│   │   ├── pages/        # UpscalePage, HistoryPage
│   │   ├── hooks/        # useSSE, useUpload
│   │   ├── stores/       # useJobStore (Zustand)
│   │   └── lib/          # api.ts (client typé), constants, utils
│   └── src-tauri/        # Shell desktop Rust
│
├── runpod-worker/         # Image Docker pour RunPod Serverless
│   ├── handler.py        # Handler Python (inférence DRCT-L)
│   ├── Dockerfile
│   └── requirements.txt
│
├── monitoring/            # Configs Prometheus, Loki, Promtail, Grafana
│   ├── prometheus/
│   ├── promtail/
│   ├── loki/
│   └── grafana/
│       └── dashboards/   # api.json, celery.json, system.json
│
├── docker-compose.yml              # Stack applicative (pg + redis + api + worker)
└── docker-compose.monitoring.yml   # Stack monitoring (overlay)
```

## Variables d'environnement

Template complet : [`.env.example`](./.env.example). Variables principales :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `DATABASE_URL` | `postgresql+asyncpg://upscaler:upscaler@localhost:5432/upscaler` | Connexion PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Broker Celery + cache SSE |
| `STORAGE_BACKEND` | `local` | `local` ou `s3` |
| `AUTH_BACKEND` | `static_token` | `static_token` ou `oidc` |
| `DEV_AUTH_TOKEN` | `dev-secret-token-change-me` | Token Bearer pour le dev |
| `UPSCALE_MODEL` | `drct-l` | Modèle SR : `drct-l` ou `hat-l` |
| `COREML_MODEL_DIR` | `models` | Dossier contenant les `.mlpackage` |
| `RUNPOD_API_KEY` | — | Clé API RunPod (dans `.env`) |
| `RUNPOD_ENDPOINT_ID` | — | ID de l'endpoint Serverless |
| `SENTRY_DSN` | — | DSN Sentry (optionnel) |

## Licence

Propriétaire — usage interne GEGM uniquement.
