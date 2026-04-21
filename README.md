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

## Workflow de développement

Trois scénarios selon ce que tu veux faire. **Tu utilises presque toujours l'approche A.**

| Approche | Quand l'utiliser | Démarrage | Hot reload |
|----------|------------------|:---------:|:----------:|
| **A — Dev itératif** (hybride) | Feature, bug fix, test, travail du quotidien | ~30 s | ✅ Vite + uvicorn `--reload` |
| **B — Simulation prod locale** (tout-Docker) | Vérifier le `backend/Dockerfile`, reproduire un bug prod | 2-5 min (build) | ❌ rebuild image sur changement |
| **C — Prod entreprise** (GHCR + pull) | Déploiement sur serveur GEGM | N/A | N/A |

---

### Approche A — Dev itératif (recommandée, 99 % du temps)

Infrastructure en containers, **applicatif en natif sur l'host**. C'est le mode le plus rapide pour itérer.

```bash
# 1. Démarrer l'infra (postgres + redis uniquement)
docker compose up -d postgres redis

# 2. Appliquer les migrations (à faire 1 fois, puis à chaque nouvelle révision)
uv run alembic upgrade head

# 3. Terminal A — API FastAPI
cd backend
LOCAL_STORAGE_PATH=/tmp/gegm-upscaler-data \
COREML_MODEL_DIR=/tmp/gegm-upscaler-models \
uv run --env-file ../.env \
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 4. Terminal B — Worker Celery
cd backend
LOCAL_STORAGE_PATH=/tmp/gegm-upscaler-data \
COREML_MODEL_DIR=/tmp/gegm-upscaler-models \
uv run --env-file ../.env \
  celery -A app.main.celery_app worker --loglevel=info --concurrency=2

# 5. Terminal C — Frontend Vite
cd frontend && npm run dev
```

**Pourquoi ces surcharges ?**

- `--env-file ../.env` : pydantic-settings cherche `.env` dans le *cwd* ; lancé depuis `backend/`, il ne trouve pas le `.env` racine. Ce flag charge explicitement le bon fichier.
- `LOCAL_STORAGE_PATH=/tmp/gegm-upscaler-data` : la valeur par défaut `/data` n'est pas writable sans sudo sur macOS/Linux. `/tmp/...` évite ça.
- `COREML_MODEL_DIR=/tmp/gegm-upscaler-models` : idem pour le répertoire des `.mlpackage` Core ML (inutilisé tant que les modèles ne sont pas convertis).

**Arrêt** : `Ctrl+C` dans chaque terminal + `docker compose down` pour l'infra.

---

### Approche B — Simulation prod locale (tout-Docker)

Tout en containers, comme en prod. Utile pour valider le Dockerfile ou reproduire un bug d'environnement.

```bash
# 1. Pré-builder l'image backend (évite le warning "pull access denied")
docker compose build

# 2. Démarrer toute la stack applicative
docker compose up -d

# 3. (Optionnel) Ajouter le monitoring
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# 4. Frontend — toujours hors container (Vite dev server reste sur l'host)
cd frontend && npm run dev

# Logs temps réel
docker compose logs -f api worker

# Arrêt
docker compose down

# Reset complet (supprime les volumes Postgres/Redis/uploads)
docker compose down -v
```

**À propos du warning `pull access denied`** : il apparaît quand Docker tente de pull `gegm-upscaler-backend:latest` avant de fallback sur le build local. Ce n'est pas une erreur — juste bruyant. Le `docker compose build` explicite en étape 1 l'élimine. Le warning disparaîtra définitivement quand le CI (`.github/workflows/docker.yml`) aura pushé l'image sur GHCR au premier tag `v*.*.*`.

---

### Approche C — Prod entreprise (future)

Déploiement sur serveur GEGM après réponse de l'infra (cf. [`INFRA_QUESTIONS.md`](./INFRA_QUESTIONS.md)).

```bash
# Sur le serveur prod
docker login ghcr.io -u <user> -p <PAT-github>

# Pull l'image publiée par le CI au dernier tag
docker compose -f docker-compose.prod.yml pull

# Démarrer
docker compose -f docker-compose.prod.yml up -d
```

Le fichier `docker-compose.prod.yml` sera créé en Phase E (préparation infra entreprise). Il remplacera le `build:` local par `image: ghcr.io/karn1zc/gegm-upscaler-backend:${RELEASE_TAG}`.

**Cycle de release** :

```bash
git tag v0.1.0 && git push --tags
# → déclenche .github/workflows/docker.yml
# → build multi-arch (amd64 + arm64)
# → push ghcr.io/karn1zc/gegm-upscaler-backend:{0.1.0, 0.1, latest}
```

---

### Services exposés (approche A ou B)

| Service | URL | Credentials |
|---------|-----|-------------|
| API FastAPI | http://localhost:8000 | Bearer `dev-secret-token-change-me` |
| API Docs (Swagger) | http://localhost:8000/api/docs | — |
| Frontend Vite | http://localhost:5173 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Loki | http://localhost:3100 | — |
| Flower | http://localhost:5555 | — |
| PostgreSQL | localhost:5432 | upscaler / upscaler |
| Redis | localhost:6379 | — |

### Commandes de base (indépendantes du scénario)

```bash
# Nouvelle migration Alembic
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head

# Commit Celery frozen (après changement de dépendances)
uv lock && uv sync --frozen
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
