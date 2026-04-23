# GEGM Upscaler

> Outil interne GEGM d'upscaling d'images par super-résolution IA.
> App web (FastAPI + React) et desktop (Tauri — macOS, Windows, Linux),
> inférence GPU cloud via RunPod Serverless, déploiement Kubernetes.

**Statut** : code prod-ready (340 tests passants, 100 % features livrées).
Déploiement en prod conditionné à la fourniture des 26 valeurs infra
listées dans [`INFRA_QUESTIONS.md`](./INFRA_QUESTIONS.md) § 0.

---

## Table des matières

1. [Aperçu & fonctionnalités](#1-aperçu--fonctionnalités)
2. [Stack technique](#2-stack-technique)
3. [Architecture en bref](#3-architecture-en-bref)
4. [Prérequis](#4-prérequis)
5. [Installation initiale](#5-installation-initiale)
6. [Build & push des images Docker (versionnées)](#6-build--push-des-images-docker-versionnées)
   - [6.A — Image backend (`gegm-upscaler-backend`)](#6a--image-backend-gegm-upscaler-backend)
   - [6.B — Image worker RunPod (`arnaudboy/gegm-upscaler-worker`)](#6b--image-worker-runpod-arnaudboygegm-upscaler-worker)
7. [Mode Dev local — dev itératif](#7-mode-dev-local--dev-itératif)
8. [Mode Prod local — simulation prod sur la machine](#8-mode-prod-local--simulation-prod-sur-la-machine)
9. [Mode Prod routinière — cluster K8s GEGM](#9-mode-prod-routinière--cluster-k8s-gegm)
10. [Build desktop Tauri (distribution)](#10-build-desktop-tauri-distribution)
11. [Qualité du code & tests](#11-qualité-du-code--tests)
12. [Documentation détaillée](#12-documentation-détaillée)
13. [Licence](#13-licence)

---

## 1. Aperçu & fonctionnalités

L'outil permet aux utilisateurs GEGM d'upscaler des images par
super-résolution IA (DRCT-L / HAT-L). L'inférence tourne :
- **Localement** (Core ML sur Apple Silicon) pour les images ≤ 5 MP — 0 coût.
- **Sur RunPod Serverless** pour les images > 5 MP — ~$0.0005 / image.

Disponible en **web** (`https://upscaler.gegmgroup.com` après déploiement)
et en **desktop natif** (Tauri macOS / Windows / Linux, auto-updater
intégré).

### Features livrées

- **Upload drag-and-drop** (HTML5 + natif Tauri) avec preview et détection MP
- **Upscale ×2 / ×4** avec routage automatique local/cloud selon la taille
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
| GPU | **Core ML** (Apple Silicon, ≤ 5 MP) + **RunPod Serverless** (cloud, > 5 MP) |
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

## 6. Build & push des images Docker (versionnées)

### ⚠️ Important — le projet utilise **deux images Docker distinctes**

Elles sont **complémentaires, pas interchangeables**. Chacune a son rôle,
son registry, son cycle de release. Il faut **les deux** à l'exécution :
ton orchestrateur appelle l'API RunPod, qui spawn un container avec
l'image worker pour faire l'upscale GPU.

| Image | Registry | Rôle | Tournée sur | Version actuelle |
|---|---|---|---|:-:|
| **`gegm-upscaler-backend`** | `ghcr.io/karn1zc/` | **Orchestrateur** — API FastAPI + SPA React + Celery | Ton Mac (dev/prod local) ou K8s GEGM | à tagguer selon le besoin |
| **`gegm-upscaler-worker`** | `docker.io/arnaudboy/` | **Inférence GPU** — DRCT-L / HAT-L, handler RunPod | RunPod Serverless (ne tourne jamais chez nous) | **v1.9** |

**Flow à chaque upscale** (identique dans les 3 modes dev/prod-local/prod-k8s) :

```
User ─▶ Orchestrateur (backend image)  ─▶  API RunPod  ─▶  Worker image (v1.9)
                                        (HTTPS,                  (container
                                         RUNPOD_API_KEY)          sur GPU A10G)
```

L'endpoint RunPod `sccttzfucc5ks1` pointe en permanence sur
`arnaudboy/gegm-upscaler-worker:v1.9`. **Tu n'y touches que si tu modifies
`runpod-worker/handler.py`, `Dockerfile`, `requirements.txt` ou les
poids.** Tous les changements backend/frontend qu'on fait habituellement
vivent dans l'image backend, pas dans l'image worker.

---

### 6.A — Image backend (`gegm-upscaler-backend`)

Embarque l'API FastAPI + le SPA Vite compilé (Dockerfile multi-stage 3
étapes). Publication sur **GHCR** avec **mirror automatique** vers le
registry GitLab GEGM si les variables CI sont configurées.

#### Approche recommandée — via CI automatique (tag git)

C'est la voie standard : un tag `v*.*.*` déclenche le build, le scan
Trivy, le push vers GHCR + GitLab, **et** le push du chart Helm OCI.

```bash
# 1. Aligner les 3 fichiers de version (package.json + tauri.conf.json + Cargo.toml)
#    Exemple : bumper vers 0.2.0
sed -i '' 's/"version": "0\.1\.0"/"version": "0.2.0"/' frontend/package.json
sed -i '' 's/"version": "0\.1\.0"/"version": "0.2.0"/' frontend/src-tauri/tauri.conf.json
sed -i '' 's/^version = "0\.1\.0"/version = "0.2.0"/' frontend/src-tauri/Cargo.toml

# 2. Commit du bump
git add frontend/package.json frontend/src-tauri/Cargo.toml frontend/src-tauri/tauri.conf.json
git commit -m "chore: bump version to 0.2.0"

# 3. Tag et push — déclenche les workflows `docker.yml` + `release-tauri.yml`
git tag v0.2.0
git push origin main --follow-tags

# 4. Suivre la CI
gh run watch --repo KaRn1zC/GEGM_Upscaler
# → ~6 min pour docker.yml, ~15 min pour release-tauri.yml (4 plateformes)
```

Tags produits par le workflow sur l'image :
- `ghcr.io/karn1zc/gegm-upscaler-backend:0.2.0` (semver exact — **à utiliser en prod**)
- `ghcr.io/karn1zc/gegm-upscaler-backend:0.2` (major.minor — floating sur les patch)
- `ghcr.io/karn1zc/gegm-upscaler-backend:latest` (seulement sur `main`)

> **⚠️ Ne jamais déployer `:latest` en prod** — utiliser toujours le tag
> semver exact (`:0.2.0`) pour garantir la reproductibilité. `latest` est
> pour les tests dev/compose uniquement.

#### Build local manuel (pour tester le Dockerfile sans pousser)

Utile pour valider un changement de `backend/Dockerfile` avant de tagger.

```bash
# Multi-arch (amd64 + arm64) — identique à ce que produit la CI
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file backend/Dockerfile \
  --tag ghcr.io/karn1zc/gegm-upscaler-backend:0.2.0-dev \
  --build-arg VITE_AUTH_MODE=dev \
  --build-arg VITE_API_BASE= \
  --load \
  .

# Mono-arch (plus rapide, pour vérifier juste la build locale)
docker build \
  --file backend/Dockerfile \
  --tag gegm-upscaler-backend:0.2.0-dev \
  --build-arg VITE_AUTH_MODE=dev \
  .
```

Build args disponibles (cf. `backend/Dockerfile`) :

| ARG | Défaut | Quand le set |
|---|---|---|
| `VITE_AUTH_MODE` | `dev` | `oidc` pour une build prod web |
| `VITE_API_BASE` | (vide) | URL absolue API si domaine ≠ de celui qui sert le SPA |
| `VITE_OIDC_ISSUER` | (vide) | URL issuer Keycloak |
| `VITE_OIDC_CLIENT_ID` | `gegm-upscaler` | — |
| `VITE_SENTRY_DSN` | (vide) | DSN frontend — vide = Sentry désactivé |
| `VITE_SENTRY_ENVIRONMENT` | `production` | `production-tauri` / `staging` |
| `VITE_APP_VERSION` | (vide) | Tag release — injecté auto par la CI |

#### Push manuel (si build local)

```bash
# 1. Login GHCR (token PAT avec scope write:packages)
echo $GITHUB_TOKEN | docker login ghcr.io -u karn1zc --password-stdin

# 2. Push
docker push ghcr.io/karn1zc/gegm-upscaler-backend:0.2.0-dev

# 3. (Optionnel) Mirror vers GitLab GEGM si accès configuré
docker tag ghcr.io/karn1zc/gegm-upscaler-backend:0.2.0-dev \
  registry.gitlab.gegm.internal/infra/gegm-upscaler/backend:0.2.0-dev
docker push registry.gitlab.gegm.internal/infra/gegm-upscaler/backend:0.2.0-dev
```

> En pratique, le mirror est fait automatiquement par le job
> `mirror-to-gitlab` de `.github/workflows/docker.yml` dès que les
> variables GitHub `GITLAB_REGISTRY_*` sont configurées.

---

### 6.B — Image worker RunPod (`arnaudboy/gegm-upscaler-worker`)

Image tournée **exclusivement sur les GPU de RunPod Serverless**, jamais
chez nous. Contient PyTorch + DRCT-L + HAT-L + le `handler.py` qui
traite les événements RunPod. Hébergée sur le compte Docker Hub personnel
`arnaudboy/` — migration vers un compte GEGM prévue en fin de parcours
(cf. `SUIVI.md`, section « Différé »).

**Ne concerne pas les changements de code backend/frontend.** Tu ne
rebuilds cette image que si tu modifies :
- `runpod-worker/handler.py`
- `runpod-worker/Dockerfile`
- `runpod-worker/requirements.txt`
- `runpod-worker/models/*.pth`
- `runpod-worker/basicsr_shim/`

#### Version actuelle déployée : `v1.9`

Vérifiable côté RunPod : dashboard Serverless → endpoint `sccttzfucc5ks1`
→ Container Image → `arnaudboy/gegm-upscaler-worker:v1.9`.

#### Procédure de bump (ex. v1.9 → v2.0)

À exécuter **uniquement** si tu as modifié un des fichiers listés
ci-dessus. Sinon, saute cette étape.

```bash
# 1. Confirmer que tu as bien des changements à pousser
git status runpod-worker/
git diff HEAD~1 -- runpod-worker/ | head

# 2. Télécharger / vérifier les 2 poids dans runpod-worker/models/
#    (non commités, trop lourds pour Git)
./runpod-worker/scripts/download_weights.sh
ls -lh runpod-worker/models/
# Attendu :
#   drct-l_x4.pth  (~486 MB) — modèle principal pour x4
#   hat-l_x2.pth   (~165 MB) — modèle principal pour x2

# 3. Build de l'image — `--platform linux/amd64` est OBLIGATOIRE sur Mac
#    Apple Silicon (M1/M2/M3/M4) : la base image RunPod n'existe qu'en
#    amd64, Docker émule via QEMU. Sans ce flag, un warning
#    `InvalidBaseImagePlatform` s'affiche (l'image produite reste valide
#    mais l'intent n'est pas explicite). Sur un host Linux amd64, le flag
#    est inutile mais ne gêne pas.
docker build --platform linux/amd64 \
  -t arnaudboy/gegm-upscaler-worker:v2.0 runpod-worker/

# 4. Test local rapide (optionnel — vérifie que le container démarre)
docker run --rm --platform linux/amd64 \
  arnaudboy/gegm-upscaler-worker:v2.0 python -c "import handler; print('OK')"

# 5. Login Docker Hub (une fois, token dans ~/.docker/config.json)
docker login

# 6. Push sur Docker Hub
docker push arnaudboy/gegm-upscaler-worker:v2.0

# 7. Mettre à jour l'endpoint RunPod pour utiliser v2.0 :
#    Dashboard → Serverless → sccttzfucc5ks1 → Edit Endpoint
#    → Container Image : arnaudboy/gegm-upscaler-worker:v2.0
#    → Save
#    → les prochains jobs tirent le nouveau tag (pull automatique au cold-start).

# 8. Vérifier : lancer un upscale depuis l'UI, le premier job en cold-start
#    prend ~1 min de plus (pull de l'image), les suivants normal.
```

#### Commandes alternatives — préserver v1.9 si besoin de rollback

Tu peux garder plusieurs tags actifs sur Docker Hub :

```bash
# Re-tagger l'image existante locale en v1.9 avant de rebuild en v2.0
docker tag arnaudboy/gegm-upscaler-worker:v1.9 \
  arnaudboy/gegm-upscaler-worker:v1.9-backup

# Build la v2.0 par-dessus
docker build --platform linux/amd64 \
  -t arnaudboy/gegm-upscaler-worker:v2.0 runpod-worker/
docker push arnaudboy/gegm-upscaler-worker:v2.0

# Si la v2.0 plante en prod, rollback immédiat :
# Dashboard RunPod → Edit Endpoint → image: v1.9 → Save
```

Doc détaillée du handler + protocole I/O + specs endpoint :
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

**Usage** : déploiement réel sur `https://upscaler.gegmgroup.com` via
Kubernetes + Helm. Procédure complète A-à-Z :
[`DEPLOYMENT.md`](./DEPLOYMENT.md).

**Prérequis** :
- Les **26 livrables infra** de [`INFRA_QUESTIONS.md § 0`](./INFRA_QUESTIONS.md)
  sont remplis (placeholders values.yaml, secrets Vault, vars GitHub,
  provisionnements Keycloak/Sentry/DNS).
- Accès `kubectl` au cluster GEGM configuré (`kubectl config current-context`
  → contexte GEGM).
- `helm` 3.16+ installé.

### Premier déploiement

```bash
# 1. Copier et remplir les placeholders (fichier local, gitignoré)
cp charts/gegm-upscaler/values.yaml values-prod.local.yaml
# → éditer toutes les entrées `<TO_FILL:...>`
grep -n "<TO_FILL:" values-prod.local.yaml   # liste exhaustive

# 2. Activer le backup CNPG si le bucket est configuré
# (dans values-prod.local.yaml → database.backup.enabled: true)

# 3. Pousser un tag → déclenche le build image + chart OCI
git tag v0.2.0 && git push --follow-tags

# 4. Attendre la CI verte (~6 min)
gh run watch --repo KaRn1zC/GEGM_Upscaler

# 5. Déployer depuis le chart OCI publié par la CI
helm upgrade --install gegm-upscaler \
  oci://ghcr.io/karn1zc/charts/gegm-upscaler \
  --version 0.2.0 \
  -n gegm-upscaler \
  -f values-prod.local.yaml \
  --wait --timeout 5m

# 6. Vérifier
kubectl -n gegm-upscaler get pods
kubectl -n gegm-upscaler logs deploy/gegm-upscaler-api --tail=50
curl -fsS https://upscaler.gegmgroup.com/api/health
```

### Mises à jour ultérieures

```bash
# Bump version + push → la CI build tout et pousse le chart OCI
git tag v0.2.1 && git push --follow-tags
gh run watch --repo KaRn1zC/GEGM_Upscaler

# Déployer la nouvelle version
helm upgrade gegm-upscaler \
  oci://ghcr.io/karn1zc/charts/gegm-upscaler \
  --version 0.2.1 \
  -n gegm-upscaler \
  -f values-prod.local.yaml \
  --wait

kubectl -n gegm-upscaler rollout status deploy/gegm-upscaler-api
kubectl -n gegm-upscaler rollout status deploy/gegm-upscaler-worker
```

### Rollback

```bash
helm history gegm-upscaler -n gegm-upscaler
helm rollback gegm-upscaler <revision> -n gegm-upscaler --wait
```

### Incident / dépannage

Playbooks complets pour les 10 alertes PrometheusRule + 3 pannes
hors-alerte (.dmg cassé, updater HS, OIDC) dans
[`RUNBOOK.md`](./RUNBOOK.md).

---

## 10. Build desktop Tauri (distribution)

Les utilisateurs finaux téléchargent un bundle natif depuis la page
**GitHub Releases** du dépôt. Trois plateformes x64 + Apple Silicon
sont produites automatiquement par la CI.

### 10.1 Mode dev (hot-reload Rust + React)

```bash
cd frontend && npm run tauri:dev
```

Démarre Vite + recompile le shell Rust à chaque modif. Requiert que
l'API backend tourne (§ 7, terminal 2).

### 10.2 Build release automatique via CI (procédure standard)

C'est la voie qui produit les bundles distribués aux users. **Déclenchée
par un tag git** `v*.*.*`.

```bash
# 1. Vérifier que les 3 fichiers sont alignés sur la même version
grep -E '"version"' frontend/package.json frontend/src-tauri/tauri.conf.json
grep -E '^version' frontend/src-tauri/Cargo.toml

# 2. Bumper (voir § 6.1 pour la commande sed)
# 3. Commit + tag + push
git tag v0.2.0 && git push --follow-tags

# 4. Suivre la CI — ~15 min pour les 4 plateformes en parallèle
gh run watch --repo KaRn1zC/GEGM_Upscaler --workflow release-tauri.yml

# 5. Une fois la CI verte, une GitHub Release **draft** est créée avec :
#    macOS   : GEGM.Upscaler_0.2.0_aarch64.dmg
#              GEGM.Upscaler_0.2.0_x64.dmg
#              GEGM.Upscaler_<arch>.app.tar.gz + .sig (updater)
#    Windows : GEGM.Upscaler_0.2.0_x64-setup.exe
#              GEGM.Upscaler_0.2.0_x64_en-US.msi
#              GEGM.Upscaler_0.2.0_x64-setup.nsis.zip + .sig (updater)
#    Linux   : GEGM.Upscaler_0.2.0_amd64.deb
#              GEGM.Upscaler_0.2.0_amd64.AppImage
#              GEGM.Upscaler_0.2.0_amd64.AppImage.sig (updater)
#    Cross   : latest.json (manifest consommé par tous les clients)

# 6. Publier la release pour que les users la voient
gh release edit v0.2.0 --repo KaRn1zC/GEGM_Upscaler --draft=false
```

Les instances déjà installées sur les machines des users détectent la
nouvelle version automatiquement (check au démarrage + bannière
« Installer et relancer »). Le bundle est téléchargé, vérifié
cryptographiquement (signature ed25519), remplacé et relancé. **Pas de
clic-droit / SmartScreen nécessaire pour les mises à jour** — seul le
tout premier lancement après install fraîche a une friction OS.

### 10.3 Build release local (pour tester un bundle avant CI)

Utile pour valider un changement Tauri sans passer par le tag CI.

**macOS (sur un Mac)**
```bash
cd frontend
npm run tauri:build
# Artefacts : frontend/src-tauri/target/release/bundle/{dmg,macos}/
```

**Windows (sur une Windows)**
```bash
cd frontend
npm run tauri:build
# Artefacts : frontend/src-tauri/target/release/bundle/{msi,nsis}/
```

**Linux (Ubuntu 22.04)**
```bash
# Deps système requises (une fois)
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.0-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev \
  libsoup-3.0-dev \
  libjavascriptcoregtk-4.0-dev \
  patchelf

cd frontend
npm run tauri:build
# Artefacts : frontend/src-tauri/target/release/bundle/{deb,appimage}/
```

### 10.4 Prérequis pour installation par les utilisateurs finaux

Guide utilisateur détaillé : [`DISTRIBUTION.md`](./DISTRIBUTION.md) § 1.

- **macOS** : télécharger `.dmg` correspondant à son Mac (aarch64 pour
  Apple Silicon / x64 pour Intel). Double-cliquer, glisser dans
  Applications, **clic-droit → Ouvrir** au premier lancement uniquement
  (Gatekeeper non signé).
- **Windows** : télécharger `.exe` ou `.msi`. Double-cliquer. Au premier
  lancement, SmartScreen → **More info** → **Run anyway** (pas de certif EV).
- **Linux** : télécharger `.deb` (`sudo dpkg -i`) ou `.AppImage`
  (`chmod +x` + double-clic).

### 10.5 Sécurité de la clé de signature updater

La clé privée Tauri ed25519 utilisée pour signer les mises à jour est
stockée dans :
- **Password manager personnel** (fichier `tauri.key` + password)
- **GitHub Secrets** du repo (`TAURI_SIGNING_PRIVATE_KEY` + `..._PASSWORD`)

⚠️ **Ne jamais régénérer cette clé** — tous les clients déjà installés
fonctionneraient alors en orphelins sans possibilité de recevoir de
mise à jour. Pour plus de détails : [`DISTRIBUTION.md`](./DISTRIBUTION.md) § 2.

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
| [`CLAUDE.md`](./CLAUDE.md) | Conventions de code + stack, pour contributeurs |
| [`frontend/CLAUDE.md`](./frontend/CLAUDE.md) | Design tokens + direction esthétique frontend |
| [`.env.example`](./.env.example) | Variables d'environnement backend documentées |
| [`charts/gegm-upscaler/values.yaml`](./charts/gegm-upscaler/values.yaml) | Config Helm commentée en ligne |
| [`runpod-worker/README.md`](./runpod-worker/README.md) | Build/deploy de l'image RunPod Serverless |

---

## 13. Licence

Propriétaire — usage interne GEGM uniquement.
