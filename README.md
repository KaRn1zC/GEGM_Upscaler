<div align="center">

<img src="./assets/banner.png" alt="GEGM Upscaler — AI Super-Resolution" width="100%"/>

<br/>

<p>
  <img src="https://img.shields.io/badge/status-prod--ready-1436DE?style=for-the-badge&labelColor=000000" alt="Status"/>
  <img src="https://img.shields.io/badge/tests-354_passing-22c55e?style=for-the-badge&labelColor=000000" alt="Tests"/>
  <img src="https://img.shields.io/badge/coverage-60%25_BE_·_53%25_FE-4F6FFF?style=for-the-badge&labelColor=000000" alt="Coverage"/>
</p>

<p>
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=000000" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white&labelColor=000000" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white&labelColor=000000" alt="React"/>
  <img src="https://img.shields.io/badge/Tauri-2.0-FFC131?style=flat-square&logo=tauri&logoColor=white&labelColor=000000" alt="Tauri"/>
  <img src="https://img.shields.io/badge/Kubernetes-Helm_3-326CE5?style=flat-square&logo=kubernetes&logoColor=white&labelColor=000000" alt="K8s"/>
</p>

<p align="center">
  <strong>Outil interne GEGM d'upscaling d'images par super-résolution IA.</strong><br/>
  <sub>App web (FastAPI + React) et desktop (Tauri — macOS, Windows, Linux),<br/>
  inférence GPU cloud via RunPod Serverless, déploiement Kubernetes.</sub>
</p>

</div>

---

## Table des matières

- [Table des matières](#table-des-matières)
- [1. Aperçu \& fonctionnalités](#1-aperçu--fonctionnalités)
  - [Features livrées](#features-livrées)
- [2. Stack technique](#2-stack-technique)
- [3. Architecture en bref](#3-architecture-en-bref)
- [4. Prérequis](#4-prérequis)
- [5. Installation initiale](#5-installation-initiale)
- [6. Images Docker du projet](#6-images-docker-du-projet)
  - [Build \& release de l'image backend](#build--release-de-limage-backend)
  - [Build \& release de l'image worker RunPod](#build--release-de-limage-worker-runpod)
- [7. Mode Dev local — dev itératif](#7-mode-dev-local--dev-itératif)
  - [Commandes par terminal](#commandes-par-terminal)
  - [Accès aux services](#accès-aux-services)
  - [Pourquoi ces variables inline ?](#pourquoi-ces-variables-inline-)
  - [Arrêt](#arrêt)
  - [Lancer le desktop Tauri en mode dev](#lancer-le-desktop-tauri-en-mode-dev)
- [8. Mode Prod local — simulation prod sur la machine](#8-mode-prod-local--simulation-prod-sur-la-machine)
  - [Commandes par terminal](#commandes-par-terminal-1)
  - [Accès aux services](#accès-aux-services-1)
  - [Arrêt](#arrêt-1)
  - [Différences avec le vrai mode prod](#différences-avec-le-vrai-mode-prod)
- [9. Mode Prod routinière — cluster K8s GEGM](#9-mode-prod-routinière--cluster-k8s-gegm)
- [10. Build desktop Tauri](#10-build-desktop-tauri)
- [11. Qualité du code \& tests](#11-qualité-du-code--tests)
  - [Backend (Python)](#backend-python)
  - [Frontend (TypeScript + React)](#frontend-typescript--react)
  - [Helm chart](#helm-chart)
  - [CI GitHub Actions](#ci-github-actions)
- [12. Documentation détaillée](#12-documentation-détaillée)
- [13. Licence](#13-licence)

---

## 1. Aperçu & fonctionnalités

L'outil permet aux utilisateurs GEGM d'upscaler des images par
super-résolution IA (DRCT-L / HAT-L). En v1, l'inférence tourne
**100 % sur RunPod Serverless** (~$0.0005 / image). L'inférence locale
Core ML sur Apple Silicon est différée v2 (bloquée upstream sur
`coremltools` 10+, cf. [`SUIVI.md`](./SUIVI.md) § 11.4 A7).

Disponible en **web** (`https://upscaler.gegmgroup.com` après déploiement)
et en **desktop natif** (Tauri macOS / Windows / Linux, auto-updater
intégré).

### Features livrées

- **Upload drag-and-drop** (HTML5 + natif Tauri) avec preview et détection MP
- **Upscale ×2 / ×4** via RunPod Serverless (routage scale → modèle côté backend)
- **Traitement batch** (file d'attente parallèle, jusqu'à 10 images)
- **Progression live** (SSE backend → UI, barres de progression liquides)
- **Galerie** : comparaison avant/après avec slider, zoom panzoom
- **Historique** : tous les jobs (completed/failed/cancelled), recherche, filtres
- **Paramètres** : facteur par défaut, modèle par défaut, langue (FR/EN), mises à jour
- **Raccourcis clavier globaux** (⌘1-5, ⌘K command palette, ⌘U upload, ⌘B batch)
- **Notifications macOS/Windows/Linux** natives à la completion des jobs
- **Auto-updater desktop** (signature ed25519, indépendant Apple/Microsoft)
- **SSO Keycloak OIDC PKCE** en prod (static token en dev)
- **GDPR** : endpoint `DELETE /api/users/me` avec cascade fichiers + audit log
- **Observability** : traces OpenTelemetry distribuées, métriques Prometheus,
  logs Loki, crashes Sentry (back + front + Tauri)

---

## 2. Stack technique

| Couche | Technologies |
|---|---|
| Backend API | **FastAPI** 0.135, Python 3.12, async SQLAlchemy 2, asyncpg |
| Worker | **Celery** 5.6 + Redis / **KeyDB** (broker + result backend + SSE cache) |
| DB | **PostgreSQL 16** (managé via CloudNativePG en prod) |
| Frontend | **React 19** + TypeScript + Vite 8 + Tailwind 4 + Zustand + motion |
| Desktop | **Tauri 2** (Rust + WKWebView), plugins notification / dialog / fs / updater |
| GPU | **RunPod Serverless** (cloud, v1). Core ML (Apple Silicon, infra prête) différé v2. |
| Modèles SR | DRCT-L (`ming053l/DRCT`), fallback HAT-L |
| Déploiement | **Kubernetes** + **Helm 3** chart, Envoy Gateway, External Secrets Operator |
| Monitoring | **OpenTelemetry** + **VictoriaMetrics** (ou Prometheus), **Grafana**, **Loki**, **Sentry** self-hosted |
| CI/CD | **GitHub Actions** (7 workflows : backend, frontend, docker, release-tauri, helm-lint, e2e, runpod-worker) |

---

## 3. Architecture en bref

```
Utilisateurs GEGM
  ├─▶ Desktop .dmg / .msi / .AppImage (Tauri)
  └─▶ Web https://upscaler.gegmgroup.com
              │
              ▼
        Envoy Gateway (HTTPRoute + TLS cert-manager)
              │
              ▼
        Pods API FastAPI ──┬──▶ CNPG Postgres (jobs, users, audit_log)
                           ├──▶ KeyDB (broker Celery + SSE pub/sub)
                           ├──▶ S3 OVH (inputs + outputs)
                           └──▶ Workers Celery ──▶ RunPod Serverless (GPU)
                                                        │
                                                        └──▶ S3 OVH (outputs)
```

**Principe d'abstraction** : chaque dépendance infra (Storage, Auth, GPU,
Secrets) est derrière une ABC Python dans `backend/app/core/`. Le code
métier ne connaît que les interfaces — swap d'implémentation via `.env`
sans modifier le code. Détails complets dans
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 4. Prérequis

| Outil | Version minimale | Usage |
|---|:-:|---|
| **Python** (via [uv](https://github.com/astral-sh/uv)) | 3.12 | Backend + worker |
| **Node.js** | 20 | Frontend + Tauri CLI |
| **Rust** (via [rustup](https://rustup.rs/)) | 1.77 | Shell Tauri desktop |
| **Docker Desktop** | 25+ | Stack locale (Postgres/Redis/monitoring) |
| **kubectl** | 1.29+ | Déploiement K8s prod (section 9) |
| **helm** | 3.16+ | Chart Helm prod (section 9) |
| **gh CLI** | 2.40+ | Releases desktop (section 10) |

Sur macOS, deps système Tauri installées automatiquement. Sur Linux,
voir § 10 pour la liste de paquets apt-get requis.

---

## 5. Installation initiale

Une seule fois après le clone :

```bash
# 1. Dépendances Python (backend + tests)
uv sync

# 2. Dépendances frontend
cd frontend && npm install && cd ..

# 3. Copie du template d'environnement — adapter les valeurs si besoin
cp .env.example .env

# 4. Démarrer Postgres + Redis en container (requis pour la suite)
docker compose up -d postgres redis

# 5. Appliquer les migrations DB
uv run alembic upgrade head
```

---

## 6. Images Docker du projet

Le projet utilise **deux images Docker distinctes** et complémentaires :

| Image | Registry | Rôle | Tournée sur | Version |
|---|---|---|---|:-:|
| **`gegm-upscaler-backend`** | `ghcr.io/karn1zc/` | API FastAPI + SPA React + Celery | Mac (dev/prod local) ou K8s GEGM | tag git `v*.*.*` |
| **`gegm-upscaler-worker`** | `docker.io/arnaudboy/` | Inférence GPU DRCT-L / HAT-L, handler RunPod | RunPod Serverless | **v2.0** |

**Flow à chaque upscale** (identique en dev / prod-local / prod-k8s) :

```
User ─▶ Orchestrateur (backend)  ─▶  API RunPod  ─▶  Worker image (v2.0)
                                  (HTTPS,                 (container
                                   RUNPOD_API_KEY)         sur GPU A10G)
```

L'endpoint RunPod `sccttzfucc5ks1` pointe en permanence sur
`arnaudboy/gegm-upscaler-worker:v2.0`. **Les changements backend/frontend
quotidiens vivent dans l'image backend, pas dans l'image worker.** Tu ne
rebuilds le worker que si tu modifies `runpod-worker/handler.py`,
`Dockerfile`, `requirements.txt` ou les poids.

### Build & release de l'image backend

Voie standard : un tag git `v*.*.*` déclenche `.github/workflows/docker.yml`
qui fait build multi-arch + Trivy scan + push GHCR + mirror GitLab + push
chart OCI. Procédure complète A-à-Z (cycle de release, rollback,
checklist) : [`DEPLOYMENT.md`](./DEPLOYMENT.md) §§ 4-6.

### Build & release de l'image worker RunPod

Procédure dédiée (commandes `docker build --platform linux/amd64`,
download des poids, push Docker Hub, mise à jour endpoint RunPod) :
[`runpod-worker/README.md`](./runpod-worker/README.md).

---

## 7. Mode Dev local — dev itératif

**Usage** : développement quotidien, features et bug fixes. Stack infra
en containers, code applicatif en natif sur l'host → hot-reload complet.

**Prérequis** : § 5 fait (deps installées, `.env` présent, migrations
appliquées).

### Commandes par terminal

Ouvre **4 terminaux** dans le dossier racine du repo.

**Terminal 1 — Infrastructure (Postgres + Redis)**
```bash
docker compose up -d postgres redis
# Vérifier : docker compose ps
# Les deux doivent être "healthy".
```

**Terminal 2 — API FastAPI**
```bash
cd backend
LOCAL_STORAGE_PATH=/tmp/gegm-upscaler-data \
COREML_MODEL_DIR=/tmp/gegm-upscaler-models \
uv run --env-file ../.env \
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# L'API écoute sur http://localhost:8000
# Docs Swagger : http://localhost:8000/api/docs
```

**Terminal 3 — Worker Celery**
```bash
cd backend
LOCAL_STORAGE_PATH=/tmp/gegm-upscaler-data \
COREML_MODEL_DIR=/tmp/gegm-upscaler-models \
uv run --env-file ../.env \
  celery -A app.main.celery_app worker --loglevel=info --concurrency=2
```

**Terminal 4 — Frontend Vite**
```bash
cd frontend && npm run dev
# L'UI web tourne sur http://localhost:5173
```

### Accès aux services

| Service | URL | Credentials |
|---|---|---|
| Web UI | http://localhost:5173 | Bearer `dev-secret-token-change-me` (auto côté frontend) |
| API FastAPI | http://localhost:8000 | Header `Authorization: Bearer dev-secret-token-change-me` |
| API Swagger | http://localhost:8000/api/docs | — |
| API Prometheus | http://localhost:8000/metrics | — |
| PostgreSQL | `localhost:5432` | `upscaler / upscaler` |
| Redis | `localhost:6379` | — |

### Pourquoi ces variables inline ?

- `--env-file ../.env` → pydantic-settings cherche `.env` dans le `cwd` ;
  lancé depuis `backend/`, il ne trouve pas le `.env` racine sans ça.
- `LOCAL_STORAGE_PATH=/tmp/...` → la valeur par défaut `/data` n'est pas
  writable sans sudo sur macOS/Linux.
- `COREML_MODEL_DIR=/tmp/...` → idem, inutile tant que les `.mlpackage`
  Core ML ne sont pas convertis (code prêt, conversion bloquée upstream
  sur `coremltools 10+`).

### Arrêt

`Ctrl+C` dans chaque terminal applicatif, puis :
```bash
docker compose down           # arrête l'infra, conserve les volumes
# ou
docker compose down -v        # arrête ET vide la DB (reset complet)
```

### Lancer le desktop Tauri en mode dev

```bash
cd frontend && npm run tauri:dev
# Lance Vite + Tauri avec hot-reload sur le code React et le code Rust.
# Requiert que l'API (terminal 2) et le worker (terminal 3) tournent déjà.
```

---

## 8. Mode Prod local — simulation prod sur la machine

**Usage** : valider le Dockerfile, reproduire un bug d'environnement,
faire tourner l'image **exacte** qui partira en prod, sur sa propre machine.

**Différence avec le dev local** : zéro code natif, tout est dans des
containers — l'image backend sert à la fois l'API et le SPA Vite compilé
via FastAPI StaticFiles.

### Commandes par terminal

**Terminal 1 — Build de l'image (une seule fois, ou après changement du code)**
```bash
# Option A — build explicite via le compose (recommandé)
docker compose build

# Option B — build manuel pour avoir un tag versionné
docker build \
  --file backend/Dockerfile \
  --tag gegm-upscaler-backend:0.2.0-local \
  --build-arg VITE_AUTH_MODE=dev \
  .
```

**Terminal 2 — Stack applicative complète**
```bash
# Infra + API + worker (images buildées en étape précédente)
docker compose up -d

# Vérifier que tout est "healthy"
docker compose ps

# Logs en temps réel
docker compose logs -f api worker
```

**Terminal 3 — (Optionnel) Stack monitoring**

Pour avoir aussi Grafana, Prometheus, Loki, Promtail et Flower en local :
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

**Terminal 4 — (Optionnel) Frontend Vite séparé**

Le SPA est déjà servi par le conteneur `api` sur le port 8000. Mais si
tu veux faire des tweaks UI sans rebuilder l'image :
```bash
cd frontend && npm run dev
# Vite tourne sur :5173 et proxy les /api/* vers :8000
```

**Terminal 5 — (Optionnel) App desktop Tauri**

Deux variantes selon ce que tu veux tester :

```bash
# Option A — Tauri dev (hot-reload, le plus rapide)
cd frontend && npm run tauri:dev
# Vite proxy /api → :8000, fenêtre native Tauri sur le SPA dev

# Option B — bundle Tauri prod local pointant sur le compose
# (produit un .dmg/.msi/.AppImage figé sur ton backend local — utile
#  pour valider l'expérience exacte du bundle final avant un tag CI)
cd frontend
VITE_API_BASE=http://localhost:8000/api \
VITE_AUTH_MODE=dev \
npm run tauri:build
# Artefacts : frontend/src-tauri/target/release/bundle/{dmg,msi,appimage}/
```

### Accès aux services

| Service | URL | Credentials |
|---|---|---|
| App complète (API + SPA) | http://localhost:8000 | `dev-secret-token-change-me` |
| API Swagger | http://localhost:8000/api/docs | — |
| Grafana (si overlay monitoring) | http://localhost:3000 | `admin / admin` |
| Prometheus | http://localhost:9090 | — |
| Loki | http://localhost:3100 | — |
| Flower (Celery UI) | http://localhost:5555 | — |
| PostgreSQL | `localhost:5432` | `upscaler / upscaler` |
| Redis | `localhost:6379` | — |

### Arrêt

```bash
docker compose down                                                    # stack app
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down  # + monitoring
docker compose down -v                                                 # reset complet (volumes purgés)
```

### Différences avec le vrai mode prod

Cette simulation **ne teste pas** :
- L'authentification OIDC Keycloak (token statique en dev)
- Le stockage S3 OVH (filesystem local)
- VictoriaMetrics / OTel collector (Prometheus local)
- La Gateway Envoy + cert-manager (exposition directe port 8000)

Pour tester ces couches, il faut passer en § 9.

---

## 9. Mode Prod routinière — cluster K8s GEGM

Déploiement réel sur `https://upscaler.gegmgroup.com` via Kubernetes +
Helm chart `charts/gegm-upscaler/`.

**Procédure complète A-à-Z** (prérequis, secrets Vault, première install,
cycle de release, rollback, observabilité, dépannage) :
**[`DEPLOYMENT.md`](./DEPLOYMENT.md)**.

**Playbooks d'astreinte** (10 alertes PrometheusRule + 3 pannes
hors-alerte + procédure restore CNPG + post-mortem) :
[`RUNBOOK.md`](./RUNBOOK.md).

**Checklist exhaustive des livrables infra** (17 placeholders chart + 8
secrets Vault + 8 GitHub vars + provisionnements Keycloak/Sentry/DNS) :
[`INFRA_QUESTIONS.md`](./INFRA_QUESTIONS.md).

---

## 10. Build desktop Tauri

Les utilisateurs téléchargent un bundle natif depuis la page **GitHub
Releases** du dépôt. Quatre plateformes (macOS aarch64 + macOS x86_64 +
Windows x86_64 + Linux x86_64) sont produites automatiquement à chaque
tag `v*.*.*` par `.github/workflows/release-tauri.yml`.

**Procédure de release complète** (cheat-sheet bump + tag + publish,
build local sans CI, rollback, plan de migration S3 OVH) :
**[`DISTRIBUTION.md`](./DISTRIBUTION.md)**.

**Mode dev rapide** :

```bash
cd frontend && npm run tauri:dev
```

Lance Vite + Tauri en hot-reload sur le code React et le code Rust.
Requiert que l'API backend tourne (cf. § 7, terminal 2).

⚠️ **Ne jamais régénérer la clé de signature updater** (`tauri.key`) —
tous les clients déjà installés deviendraient incapables de recevoir des
mises à jour. Détails : [`DISTRIBUTION.md`](./DISTRIBUTION.md) § 2.

---

## 11. Qualité du code & tests

Le projet tourne avec **zéro warning** sur lint/type/tests.

### Backend (Python)

```bash
uv run ruff check backend/              # linter
uv run ruff format --check backend/     # vérif formatage
uv run mypy backend/app/                # type check strict
uv run pytest backend/tests/            # 155 tests (<5 s)
uv run pytest --cov=backend/app --cov-report=html backend/tests/
```

### Frontend (TypeScript + React)

```bash
cd frontend
npm run lint                # ESLint
npx tsc -b                  # type check
npm test -- --run           # 185 tests Vitest (<5 s)
npm run test:coverage       # couverture V8
npm run test:e2e            # 14 tests Playwright
```

### Helm chart

```bash
helm lint charts/gegm-upscaler
helm template gegm-upscaler charts/gegm-upscaler -f values-prod.local.yaml \
  | kubectl --dry-run=server apply -f -
```

### CI GitHub Actions

7 workflows s'exécutent automatiquement :

| Workflow | Trigger | Contenu |
|---|---|---|
| `backend.yml` | PR touchant `backend/**` | ruff + mypy + pytest avec services Postgres + Redis + alembic |
| `frontend.yml` | PR touchant `frontend/**` | ESLint + tsc + vitest |
| `e2e.yml` | PR touchant `frontend/**` | Playwright avec Vite webServer |
| `helm-lint.yml` | PR touchant `charts/**` | `helm lint` + `helm template` |
| `docker.yml` | Tag `v*.*.*` | Build multi-arch + Trivy scan + push GHCR + mirror GitLab + chart OCI push |
| `release-tauri.yml` | Tag `v*.*.*` | Build desktop macOS + Linux + Windows + signature updater + GitHub Release draft |
| `runpod-worker.yml` | PR touchant `runpod-worker/**` | Build image RunPod worker |

---

## 12. Documentation détaillée

| Fichier | Contenu |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Spec complète, ADR, décisions de stack |
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Guide A-à-Z déploiement K8s (checklist, secrets, rollback) |
| [`DISTRIBUTION.md`](./DISTRIBUTION.md) | Procédure release desktop, updater ed25519, install utilisateurs |
| [`RUNBOOK.md`](./RUNBOOK.md) | Playbooks incident par alerte + procédure restore CNPG + post-mortem |
| [`GRAFANA_OAUTH.md`](./GRAFANA_OAUTH.md) | Intégration SSO Keycloak pour Grafana |
| [`INFRA_QUESTIONS.md`](./INFRA_QUESTIONS.md) | Checklist exhaustive des livrables infra en attente |
| [`SUIVI.md`](./SUIVI.md) | Tracking d'avancement par phase, todolist, finitions post-prod |
| [`.env.example`](./.env.example) | Variables d'environnement backend documentées |
| [`charts/gegm-upscaler/values.yaml`](./charts/gegm-upscaler/values.yaml) | Config Helm commentée en ligne |
| [`runpod-worker/README.md`](./runpod-worker/README.md) | Build/deploy de l'image RunPod Serverless |

---

## 13. Licence

Propriétaire — usage interne GEGM uniquement.
